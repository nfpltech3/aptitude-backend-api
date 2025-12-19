from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models, crud
from services.timer import is_time_over
from schemas import SaveAnswerRequest, SubmitRequest
from fastapi import BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

# --- Service Imports ---
from services.zoho_questions import fetch_all_zoho_questions
from services.question_mapper import sanitize_questions
from services.zoho_candidate import fetch_candidate_by_token
from services.grading import calculate_score
from services.zoho_sync import update_candidate_summary, push_candidate_answers, mark_test_started
from services.timer import get_ist_time

from dotenv import load_dotenv
import os, json, random
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

models.Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all domains (Safe for dev/ngrok)
    allow_credentials=True,
    allow_methods=["*"],  # Allows GET, POST, etc.
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ViolationRequest(BaseModel):
    token: str
    reason: str

@app.get("/")
def home():
    return "Backend running"

@app.get("/api/check-token")
def check_candidate_token(token: str, db: Session = Depends(get_db)):
    """
    Verifies the token without starting the timer.
    Returns candidate name and instructions.
    """
    # Check if session already exists (Student is resuming)
    existing_session = crud.get_session_by_token(db, token)
    if existing_session:
        if existing_session.status in ["Submitted", "Auto-Submitted"]:
             # Return a specific status that the frontend understands
             return {"status": "Submitted", "name": "Candidate"}
        return {"status": "Resuming", "name": "Candidate"}

    # If new, fetch from Zoho to validate
    alloc = fetch_candidate_by_token(token)
    if not alloc:
        raise HTTPException(status_code=404, detail="Invalid token")

    # Validate Status
    token_status = alloc.get("Token_Status") or alloc.get("Token_Status1") 
    if token_status and token_status != "Valid":
         raise HTTPException(status_code=403, detail="Token is Invalid")

    # Get Name safely
    name_data = alloc.get("Candidate_Name")
    candidate_name = name_data.get("display_value") if isinstance(name_data, dict) else name_data

    return {
        "status": "New", 
        "name": candidate_name,
        "instructions": "Please do not refresh the page once started."
    }

@app.post("/api/record-violation")
def record_violation(data: ViolationRequest, db: Session = Depends(get_db)):
    """
    Logs proctoring violations sent from the frontend.
    """
    # 1. Fetch the session
    session = crud.get_session_by_token(db, data.token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2. Log it (Print to console or save to a file/DB)
    # Ideally, you would have a Violation table, but for now, printing is enough for testing.
    print(f"⚠️ [VIOLATION] Candidate: {session.candidate_id} | Reason: {data.reason}")

    # Optional: You could save this to a text file if you want a permanent record
    # with open("violations.log", "a") as f:
    #     f.write(f"{get_ist_time()} - {session.candidate_id} - {data.reason}\n")

    return {"status": "logged"}

@app.post("/api/start-test")
def start_test_session(data: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    token = data.get("token", "").strip()

    # 1. Fetch Candidate
    alloc = fetch_candidate_by_token(token)
    if not alloc:
        raise HTTPException(status_code=404, detail="Invalid token")
    
    # 2. Extract Details
    try:
        pos_data = alloc.get("Position_Applied")
        if isinstance(pos_data, dict):
            candidate_position_id = int(pos_data.get("ID", 0))
            position_name = pos_data.get("display_value", "")
        else:
            candidate_position_id = int(pos_data) if pos_data else 0
            position_name = "Unknown"
        
        # Duration Logic
        zoho_duration = alloc.get("Test_Duration_Minutes")
        if zoho_duration:
             duration_mins = int(zoho_duration)
        else:
            duration_mins = 40
    
    except Exception as e:
        raise HTTPException(status_code=500, detail="Data Error")

    # 3. Create Session (OR Fetch if exists)
    session = crud.get_session_by_token(db, token)

    if not session:
        # timer starts here
        session = crud.create_session(
            db, 
            token=token, 
            zoho_id=alloc["ID"], 
            duration_mins=duration_mins
        )
        
        # disable to reduce api call
        # try:
        #     background_tasks.add_task(mark_test_started, alloc["ID"])
        # except Exception as e:
        #     print(f"Warning: Could not sync start time: {e}")
    
    # 4. Fetch Questions
    if not session.question_cache:
        raw_questions = fetch_all_zoho_questions()
        
        # B. Clean & Standardize Data
        all_questions_clean = []
        for q in raw_questions:
            
            raw_sub = q.get("Position_Relevant_To")
            z_sub = "General"
            
            if isinstance(raw_sub, dict):
                # Case 1: It's a Dictionary
                z_sub = raw_sub.get("display_value", "General")
                
            elif isinstance(raw_sub, list) and len(raw_sub) > 0:
                # Case 2: It's a List
                first_item = raw_sub[0]
                if isinstance(first_item, dict):
                    z_sub = first_item.get("display_value", "General")
                else:
                    z_sub = str(first_item)
                    
            elif raw_sub and str(raw_sub).lower() != "null":
                # Case 3: It's just a String
                z_sub = str(raw_sub)

            # Handle Options
            opts = [
                str(q.get("Option_A", "")).strip(),
                str(q.get("Option_B", "")).strip(),
                str(q.get("Option_C", "")).strip(),
                str(q.get("Option_D", "")).strip()
            ]
            
            # Handle Correct Answer Text
            correct_code = q.get("Correct_Answer")
            correct_text = correct_code
            if correct_code == "A": correct_text = opts[0]
            elif correct_code == "B": correct_text = opts[1]
            elif correct_code == "C": correct_text = opts[2]
            elif correct_code == "D": correct_text = opts[3]

            all_questions_clean.append({
                "id": str(q.get("ID")),
                "text": q.get("Question_Text"),
                "type": q.get("Question_Type", "MCQ"),
                "topic": q.get("Topic"),
                "sub_topic": z_sub,
                "options": [o for o in opts if o],
                "correct_mcq": correct_text,
                "correct_desc": q.get("Correct_Descriptive_Answer2", ""),
                "max_marks": int(q.get("Max_Marks", 1) or 1)
            })

        # C. Select Questions based on Blueprint
        selected_questions = []
        blueprint = {"Aptitude": 5, "Numerical": 5, "Verbal": 5}
        
        for topic, count in blueprint.items():
            qs_in_topic = [q for q in all_questions_clean if q["topic"] == topic]
            if len(qs_in_topic) <= count:
                selected_questions.extend(qs_in_topic)
            else:
                selected_questions.extend(random.sample(qs_in_topic, count))

        # -- Departmental Logic --
        has_dept_test = alloc.get("Has_Department_Test")
        if has_dept_test == "Yes" or has_dept_test == True:
            dept_qs = []
            c_pos = position_name.lower()
            
            for q in all_questions_clean:
                if q["topic"] == "Departmental":
                    q_tag = q["sub_topic"].lower()
                    if (q_tag in c_pos) or (c_pos in q_tag):
                        dept_qs.append(q)

            
            if len(dept_qs) <= 10:
                selected_questions.extend(dept_qs)
            else:
                selected_questions.extend(random.sample(dept_qs, 10))

        # D. Sort
        topic_priority = {"Aptitude": 1, "Numerical": 2, "Verbal": 3, "Departmental": 4}
        selected_questions.sort(key=lambda q: topic_priority.get(q["topic"], 99))

        # E. Prepare Cache (Frontend & Grading)
        safe_cache = []
        grading_cache = {}

        for q in selected_questions:
            q_id = q["id"]
            
            safe_cache.append({
                "question_id": q_id,
                "text": q["text"],
                "type": q["type"],
                "topic": q["topic"],
                "options": q["options"]
            })
            
            grading_cache[q_id] = {
                "type": q["type"],
                "correct_mcq": q["correct_mcq"],
                "correct_desc": q.get("correct_desc", ""),
                "max_marks": q["max_marks"],
                "topic": q["topic"] 
            }

        session.question_cache = safe_cache
        session.grading_cache = grading_cache
        db.commit()
    
    # 5. Calculate Remaining Time
    now_ist = get_ist_time()
    remaining_delta = session.end_time - now_ist
    remaining_seconds = max(0, int(remaining_delta.total_seconds()))

    # Fetch Saved Answers (if any)
    saved_answers_query = db.query(models.Answer).filter(models.Answer.session_id == session.id).all()
    saved_map = {str(a.question_id): a.answer_text for a in saved_answers_query}

    return {
        "end_time": session.end_time.isoformat(),
        "remaining_seconds": remaining_seconds,
        "questions": session.question_cache,
        "saved_answers": saved_map
    }

@app.get("/start-test", response_class=HTMLResponse)
def serve_test_page(request: Request, token: str):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/save-answer")
def save_answer(data: SaveAnswerRequest, db: Session = Depends(get_db)):
    # 1. Validate Session & Time
    session = crud.get_session_by_token(db, data.token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if is_time_over(session):
        raise HTTPException(status_code=403, detail="Time is over")
    
    if session.status != "In-Progress":
        raise HTTPException(status_code=403, detail="Test already submitted")

    safe_qid = int(data.question_id)

    # 2. Check if answer already exists (Upsert)
    existing_answer = db.query(models.Answer).filter(
        models.Answer.session_id == session.id,
        models.Answer.question_id == safe_qid
    ).first()

    if existing_answer:
        # Update existing
        existing_answer.answer_text = data.answer_text
        # Optional: Update 'saved_at' timestamp if you have that column
        existing_answer.saved_at = get_ist_time()
    else:
        # Insert new
        new_answer = models.Answer(
            session_id=session.id,
            question_id=safe_qid,
            answer_text=data.answer_text
        )
        db.add(new_answer)
    
    db.commit()
    return {"status": "saved"}

@app.post("/submit-test")
def submit_test(data: SubmitRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    session = crud.get_session_by_token(db, data.token)
    if not session:
        raise HTTPException(status_code=404, detail="Invalid token")

    # Prevent double submission
    if session.status != "In-Progress":
        return {"status": session.status, "message": "Test already submitted"}

    # 1. Determine Status
    now_ist = get_ist_time()
    is_timeout = is_time_over(session)
    session.status = "Auto-Submitted" if is_timeout else "Submitted"
    session.submission_type = "Timer" if is_timeout else "Manual"

    if hasattr(session, "submitted_at"):
        session.submitted_at = now_ist
    
    # 2. Calculate Score (MCQ)
    final_score, score_breakdown = calculate_score(session, db)
    session.total_score = final_score

    db.commit()
    db.refresh(session)
    
    # 3. Gather Answers for Zoho
    all_answers = db.query(models.Answer).filter(models.Answer.session_id == session.id).all()
    q_front_map = {str(q["question_id"]): q for q in session.question_cache}
    q_grade_map = session.grading_cache

    answers_payload = []
    for a in all_answers:
        q_id = str(a.question_id)
        q_data = q_front_map.get(q_id, {})
        q_grade_data = q_grade_map.get(q_id, {})

        awarded = score_breakdown.get(q_id, 0)
        max_m = q_grade_data.get("max_marks", 1)
        
        answers_payload.append({
            "question_id": q_id,
            "question_text": q_data.get("text", "Unknown"),
            "question_type": q_data.get("type", "MCQ"),
            "topic": q_data.get("topic", "General"),
            "answer_text": a.answer_text,
            "marks_awarded": awarded, 
            "max_marks": max_m
        })
    
    zoho_status = "Submitted"
    time_payload = session.end_time

    # 4. RUN SYNC IN BACKGROUND
    background_tasks.add_task(
        perform_zoho_sync,
        session.candidate_id,
        final_score,
        zoho_status,
        time_payload,
        answers_payload
    )

    return {"status": session.status, "score": final_score}

def perform_zoho_sync(candidate_id, score, status, end_time, answers):
    try:
        print(f"Starting Background Sync for {candidate_id}...")
        
        update_candidate_summary(
            zoho_id=candidate_id, 
            mcq_score=score, 
            status=status,
            scheduled_end_time=end_time,
            answers_list=answers
        )
        
        # # B. Push Answers -> Disabled to save api calls
        # if answers:
        #     push_candidate_answers(candidate_id, answers)
        
    except Exception as e:
        print(f"CRITICAL: Background Sync Failed for {candidate_id}: {e}")
