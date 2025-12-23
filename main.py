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

app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ViolationRequest(BaseModel):
    token: str
    reason: str

class CandidateWebhook(BaseModel):
    token: str
    zoho_id: str
    name: str
    duration: int
    position: str
    has_dept_test: str # "Yes" or "No"

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"status": "alive", "msg": "Backend running"}

@app.get("/api/check-token")
def check_candidate_token(token: str, db: Session = Depends(get_db)):
    token = token.strip()

    # 1. OPTIMIZED PATH (Check Local DB)
    session = crud.get_session_by_token(db, token)
    if session:
        if session.status in ["Submitted", "Auto-Submitted"]:
             return {"status": "Submitted", "name": session.candidate_name}
        
        if session.status == "In-Progress":
             return {
                 "status": "Resuming", 
                 "name": session.candidate_name,
                 "instructions": "Resuming test..."
             }
        
        # If Allocated (New), allow entry
        return {"status": "New", "name": session.candidate_name, "instructions": "..."}

    # 2. FALLBACK PATH (Call Zoho if DB is empty/wiped)
    print(f"⚠️ Session missing for {token}. Attempting Fallback Fetch...")
    
    alloc = fetch_candidate_by_token(token)
    if not alloc:
        raise HTTPException(status_code=404, detail="Invalid token")

    token_status = alloc.get("Token_Status") or alloc.get("Token_Status1") 
    if token_status and token_status != "Valid":
         raise HTTPException(status_code=403, detail="Token is Invalid")

    # Extract Data
    zoho_duration = alloc.get("Test_Duration_Minutes")
    duration_mins = int(zoho_duration) if zoho_duration else 40

    name_data = alloc.get("Candidate_Name")
    candidate_name = name_data.get("display_value") if isinstance(name_data, dict) else name_data
    # Safety fallback if name is somehow None
    if not candidate_name: candidate_name = "Candidate"

    # Position Logic
    pos_data = alloc.get("Position_Applied")
    position_name = "Unknown"
    if isinstance(pos_data, dict):
        if "display_value" in pos_data: position_name = pos_data["display_value"]
        elif "Postion" in pos_data: position_name = pos_data["Postion"]
        elif "Role_Name" in pos_data: position_name = pos_data["Role_Name"]
    elif isinstance(pos_data, str):
         if len(pos_data) < 20 and not pos_data.isdigit(): position_name = pos_data

    raw_dept_flag = alloc.get("Has_Department_Test")
    has_dept_test = "Yes" if (raw_dept_flag == "Yes" or raw_dept_flag is True) else "No"

    # Save to DB (So next time we hit the Optimized Path)
    crud.create_placeholder_session(
        db, 
        token=token, 
        zoho_id=alloc["ID"], 
        duration_mins=duration_mins,
        position_name=position_name,
        has_dept_test=has_dept_test,
        candidate_name=candidate_name
    )

    return {
        "status": "New", 
        "name": candidate_name, # Return the name we just extracted
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
def start_test_session(data: dict, db: Session = Depends(get_db)):
    token = data.get("token", "").strip()

    # 1. Fetch Session from Local DB (Fast)
    session = crud.get_session_by_token(db, token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please reload.")

    # 2. Activate Timer (If not already running)
    if session.status == "Allocated":
        crud.start_session_timer(db, session, session.duration_minutes)
    
    # 3. Fetch Questions (from Cache)
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
            correct_code = str(q.get("Correct_Answer", "")).strip()
            correct_text = correct_code
            if correct_code == "A" and len(opts) > 0: correct_text = opts[0]
            elif correct_code == "B" and len(opts) > 1: correct_text = opts[1]
            elif correct_code == "C" and len(opts) > 2: correct_text = opts[2]
            elif correct_code == "D" and len(opts) > 3: correct_text = opts[3]

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
        if session.has_department_test == "Yes":
            dept_qs = []
            
            # Use saved position name
            c_pos = (session.position_name or "").lower()
            
            if c_pos:
                for q in all_questions_clean:
                    if q["topic"] == "Departmental":
                        q_tag = q["sub_topic"].lower()
                        # Fuzzy match
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
    
    # 4. Calculate Remaining Time
    now_ist = get_ist_time()
    if not session.end_time:
         # Fallback safety
         crud.start_session_timer(db, session, 40)
    remaining_delta = session.end_time - now_ist
    remaining_seconds = max(0, int(remaining_delta.total_seconds()))

    # Fetch Saved Answers (if any)
    saved_answers_query = db.query(models.Answer).filter(models.Answer.session_id == session.id).all()
    saved_map = {str(a.question_id): a.answer_text for a in saved_answers_query}

    return {
        "end_time": session.end_time.isoformat(),
        "remaining_seconds": remaining_seconds,
        "questions": session.question_cache,
        "saved_answers": saved_map,
        "candidate_name": session.candidate_name,
        "candidate_id": session.candidate_id
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

    safe_qid = data.question_id

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

@app.post("/api/webhook/add-candidate")
def add_candidate_webhook(data: CandidateWebhook, db: Session = Depends(get_db)):
    """
    Zoho calls this immediately after adding a candidate.
    We save them to DB so 'Check Token' doesn't need to call API later.
    """
    crud.create_placeholder_session(
        db, 
        token=data.token, 
        zoho_id=data.zoho_id, 
        duration_mins=data.duration,
        position_name=data.position,
        has_dept_test=data.has_dept_test,
        candidate_name=data.name
    )
    return {"status": "success"}