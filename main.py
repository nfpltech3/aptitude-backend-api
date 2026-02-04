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
from datetime import datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

models.Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
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
    # position: str
    test_id: str
    test_name: str
    has_dept_test: str

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"status": "alive", "msg": "Backend running"}

def mark_token_expired_in_zoho(zoho_id: str):
    try:
        from services.zoho_sync import patch_candidate_fields

        patch_candidate_fields(
            zoho_id,
            {
                "Token_Status": "Expired"
            }
        )
        print(f"Token marked expired in Zoho for ID {zoho_id}")
    except Exception as e:
        print(f"Failed to mark token expired for {zoho_id}: {e}")

@app.get("/api/check-token")
def check_candidate_token(token: str, device_id: str = None, background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    token = token.strip()

    # 1. Check if token exists in DB
    session = crud.get_session_by_token(db, token)
    now = get_ist_time()

    ref_time = None
    zoho_id = None
    alloc = None
    
    if session:
        ref_time = session.start_time if session.start_time else get_ist_time()
        zoho_id = session.candidate_id
    else:
        alloc = fetch_candidate_by_token(token)
        if not alloc:
            raise HTTPException(status_code=404, detail="Invalid token")

        zoho_id = str(alloc["ID"])
        link_sent_on = alloc.get("Link_Sent_On")
        if link_sent_on:
            ref_time = datetime.strptime(link_sent_on, "%d-%b-%Y %H:%M:%S")

    if ref_time and now > ref_time + timedelta(hours=24):
        if background_tasks:
            background_tasks.add_task(mark_token_expired_in_zoho, zoho_id)

        raise HTTPException(
            status_code=403,
            detail="This test link has expired. Please contact HR."
        )
    
    if session:
        if session.status in ["Submitted", "Auto-Submitted"]:
            # Block if already submitted
            return {
                "status": "Already-Submitted", 
                "name": session.candidate_name,
                "message": "This test has already been completed and cannot be reopened."
            }
        
        if session.status == "In-Progress":
            if not session.device_id:
                # Edge case: test started but device_id wasn't saved (old version)
                session.device_id = device_id
                db.commit()
                return {
                    "status": "Resuming", 
                    "name": session.candidate_name, 
                    "instructions": "Resuming test..."
                }
                
            if session.device_id == device_id:
                return {
                    "status": "Resuming", 
                    "name": session.candidate_name, 
                    "instructions": "Resuming test..."
                }
            else:
                # Different device detected!
                return {
                    "status": "Device-Locked", 
                    "name": session.candidate_name, 
                    "message": "This test is active on another device. You cannot access it from here.",
                    "instructions": "Please use the original device/browser to continue."
                }
        
        # Allocated status - fresh start allowed
        if session.status == "Allocated":
            return {
                "status": "New", 
                "name": session.candidate_name, 
                "instructions": "Click 'Start Assessment' to begin."
            }
            
    token_status = alloc.get("Token_Status")
    if token_status and token_status != "Valid":
        raise HTTPException(status_code=403, detail="This link has been invalidated.")
    
    zoho_duration = alloc.get("Test_Duration_Minutes")
    duration_mins = int(zoho_duration) if zoho_duration else 40
    
    name_data = alloc.get("Candidate_Name")
    candidate_name = name_data.get("display_value") if isinstance(name_data, dict) else name_data or "Candidate"

    # pos_data = alloc.get("Position_Applied")
    test_data = alloc.get("Select_Test_Paper")
    test_name = None
    test_id = None
    
    # position_name = "Unknown"
    if isinstance(test_data, dict):
        test_name = test_data.get("display_value")
        test_id = test_data.get("ID")

    raw_dept_flag = alloc.get("Has_Department_Test")
    has_dept_test = "Yes" if (raw_dept_flag == "Yes" or raw_dept_flag is True) else "No"

    crud.create_placeholder_session(
        db, 
        token=token, 
        zoho_id=alloc["ID"],
        test_id=test_id,
        test_name=test_name,
        duration_mins=duration_mins,
        # position_name=position_name,
        has_dept_test=has_dept_test,
        candidate_name=candidate_name
    )

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
    session = crud.get_session_by_token(db, data.token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    new_count = crud.increment_violation(db, session.id)

    print(f"⚠️ [VIOLATION] Candidate: {session.candidate_name} | Total: {new_count} | Reason: {data.reason}")

    return {"status": "logged", "current_violations": new_count}

@app.post("/api/start-test")
def start_test_session(data: dict, db: Session = Depends(get_db)):
    token = data.get("token", "").strip()
    device_id = data.get("device_id")

    # 1. Fetch Session
    session = crud.get_session_by_token(db, token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please reload.")

    # Prevent starting if already submitted
    if session.status in ["Submitted", "Auto-Submitted"]:
        raise HTTPException(
            status_code=403, 
            detail="This test has already been submitted and cannot be restarted."
        )
        
    if session.status == "In-Progress":
        if session.device_id and session.device_id != device_id:
            raise HTTPException(
                status_code=403,
                detail="Test is active on another device. Access denied."
            )
    
    if not session.device_id:
        session.device_id = device_id
        db.commit()
    
    # 2. Activate Timer (If not already running)
    if session.status == "Allocated":
        crud.start_session_timer(db, session, session.duration_minutes)
    
    # 3. Fetch/Generate Questions
    if True: # always regenerate for now
        raw_questions = fetch_all_zoho_questions()
        
        # B. Clean & Standardize Data
        all_questions_clean = []
        for q in raw_questions:
            # raw_sub = q.get("Test_Question_Mapping")
            raw_mapping = q.get("Test_Question_Mapping")
            # z_sub = "General"
            mapped_paper_id = ""
            
            if isinstance(raw_mapping, dict):
                # Case 1: It's a Dictionary
                mapped_paper_id = raw_mapping.get("ID", "")
                
            elif isinstance(raw_mapping, list) and len(raw_mapping) > 0:
                # Case 2: It's a List
                mapped_paper_id = raw_mapping[0].get("ID", "")
                    
            # elif raw_sub and str(raw_sub).lower() != "null":
            #     # Case 3: It's just a String
            #     z_sub = str(raw_sub)

            opts = [
                str(q.get("Option_A", "")).strip(),
                str(q.get("Option_B", "")).strip(),
                str(q.get("Option_C", "")).strip(),
                str(q.get("Option_D", "")).strip()
            ]
            
            correct_letter = str(q.get("Correct_Answer", "")).strip().upper()

            all_questions_clean.append({
                "id": str(q.get("ID")),
                "text": q.get("Question_Text"),
                "type": q.get("Question_Type", "MCQ"),
                "topic": q.get("Topic"),
                # "sub_topic": z_sub,
                "paper_id": mapped_paper_id,
                "options": [o for o in opts if o],
                "correct_mcq": correct_letter,
                "correct_desc": q.get("Correct_Descriptive_Answer", ""),
                "max_marks": int(q.get("Max_Marks", 1) or 1)
            })

        # Select Questions
        all_eligible_questions = []
        standard_topics = ["Numerical", "Verbal"]
        
        for q in all_questions_clean:
            if q["topic"] in standard_topics:
                all_eligible_questions.append(q)
        
        # -- Departmental Logic --
        if session.has_department_test == "Yes":
            c_pos = (session.test_id or "").strip().lower()
            
            if c_pos:
                for q in all_questions_clean:
                    if q["topic"] == "Departmental":
                        q_tag = q["paper_id"].lower()
                        # Fuzzy match
                        if (q_tag in c_pos) or (c_pos in q_tag):
                            all_eligible_questions.append(q)

        # Shuffle the entire pool initially
        random.shuffle(all_eligible_questions)

        # D. Sort by Topic Priority
        topic_priority = {"Numerical": 1, "Verbal": 2, "Departmental": 3}
        selected_questions = sorted(
            all_eligible_questions, 
            key=lambda q: topic_priority.get(q["topic"], 99)
        )

        # Prepare Cache
        safe_cache = []
        grading_cache = {}

        for q in selected_questions:
            q_id = q["id"]
            safe_cache.append({
                "question_id": q_id,
                "text": q["text"],
                "type": q["type"],
                "topic": q["topic"],
                "options": q["options"],
                "max_marks": q["max_marks"]
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
    
    # If time is already over, auto-submit
    if remaining_seconds <= 0:
        session.status = "Auto-Submitted"
        session.submission_type = "Timer"
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="Test time has expired. The test has been auto-submitted."
        )

    # Fetch Saved Answers (if any)
    saved_answers_query = db.query(models.Answer).filter(models.Answer.session_id == session.id).all()
    saved_map = {str(a.question_id): a.answer_text for a in saved_answers_query}

    return {
        "status": session.status,
        "end_time": session.end_time.isoformat(),
        "remaining_seconds": remaining_seconds,
        "questions": session.question_cache,
        "saved_answers": saved_map,
        "candidate_name": session.candidate_name,
        "candidate_id": session.candidate_id
    }

@app.get("/start-test", response_class=HTMLResponse)
async def serve_test_page(request: Request, token: str, db: Session = Depends(get_db)):
    # 1. Fetch Session from Local DB
    session = crud.get_session_by_token(db, token)
    
    # 2. If no session exists, we can still serve index.html 
    # and let the frontend JS handle the "Invalid Token" message
    if not session:
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "token": token,
            "error": "Invalid or Expired Token" 
        })

    # 3. Serve your single index.html file
    return templates.TemplateResponse("index.html", {
        "request": request,
        "token": token,
        "candidate_name": session.candidate_name,
        "test_name": session.test_name,
        "position": session.test_name
    })

@app.post("/save-answer")
def save_answer(data: SaveAnswerRequest, db: Session = Depends(get_db)):
    from sqlalchemy.exc import IntegrityError
    
    # 1. Validate Session & Time
    session = crud.get_session_by_token(db, data.token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if is_time_over(session):
        raise HTTPException(status_code=403, detail="Time is over")
    
    if session.status != "In-Progress":
        raise HTTPException(status_code=403, detail="Test already submitted")

    safe_qid = data.question_id

    # 2. Check if answer already exists (Upsert with race condition handling)
    existing_answer = db.query(models.Answer).filter(
        models.Answer.session_id == session.id,
        models.Answer.question_id == safe_qid
    ).first()

    if existing_answer:
        # Update existing
        existing_answer.answer_text = data.answer_text
        existing_answer.saved_at = get_ist_time()
        db.commit()
    else:
        # Try to insert new - handle race condition
        try:
            new_answer = models.Answer(
                session_id=session.id,
                question_id=safe_qid,
                answer_text=data.answer_text
            )
            db.add(new_answer)
            db.commit()
        except IntegrityError:
            # Race condition: another request inserted first
            # Rollback and update instead
            print(f"⚡ Race condition caught for session={session.id}, question={safe_qid} - retrying as UPDATE")
            db.rollback()
            existing_answer = db.query(models.Answer).filter(
                models.Answer.session_id == session.id,
                models.Answer.question_id == safe_qid
            ).first()
            if existing_answer:
                existing_answer.answer_text = data.answer_text
                existing_answer.saved_at = get_ist_time()
                db.commit()
    
    return {"status": "saved"}

@app.post("/submit-test")
def submit_test(data: SubmitRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    session = crud.get_session_by_token(db, data.token)
    if not session:
        raise HTTPException(status_code=404, detail="Invalid token")

    # Prevent double submission
    if session.status not in ["In-Progress", "Started", "Resuming"]:
        return {"status": session.status, "message": "Test is no longer active"}

    # 1. Determine Status
    now_ist = get_ist_time()
    is_timeout = is_time_over(session)
    session.status = "Submitted" if is_timeout else "Submitted"
    session.submission_type = "Timer" if is_timeout else "Manual"

    if hasattr(session, "submitted_at"):
        session.submitted_at = now_ist
    
    # 2. Calculate Score (MCQ)
    final_score, answers_list, total_possible = calculate_score(session, db)
    
    session.total_score = final_score

    db.commit()
    db.refresh(session)
    
    # 3. Gather Answers for Zoho
    zoho_status = session.status
    time_payload = session.end_time
    
    # 4. RUN SYNC IN BACKGROUND
    background_tasks.add_task(
        perform_zoho_sync,
        session.candidate_id,
        final_score,
        zoho_status,
        session.start_time,
        time_payload,
        session.has_department_test,
        total_possible,
        session.violation_count,
        answers_list,
        session.id
    )

    return {"status": session.status, "score": final_score}

def perform_zoho_sync(candidate_id, score, status, start_time, end_time, has_dept_test, total_possible, violations, answers, session_id):
    db = SessionLocal()
    print(f"🔁 Starting Zoho sync for session {session_id}")
    try:
        success = update_candidate_summary(
            zoho_id=candidate_id, 
            mcq_score=score, 
            status=status,
            start_time=start_time,
            scheduled_end_time=end_time,
            has_dept_test=has_dept_test,
            total_possible_marks=total_possible,
            violations=violations,
            answers_list=answers
        )
        print(f"✅ Zoho update response: {success}")
        
        if success:
            session_rec = db.query(models.TestSession).filter(models.TestSession.id == session_id).first()
            if session_rec:
                session_rec.is_synced = True
                db.commit()
                print(f"✅ Successfully marked {candidate_id} as Synced in Neon.")
        
        # # B. Push Answers -> Disabled to save api calls
        # if answers:
        #     push_candidate_answers(candidate_id, answers)
        
    except Exception as e:
        print(f"❌ Zoho sync failed for session {session_id}: {e}")
    
    finally:
        db.close()

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
        # position_name=data.position,
        test_id=data.test_id,
        test_name=data.test_name,
        has_dept_test=data.has_dept_test,
        candidate_name=data.name
    )
    return {"status": "success"}

@app.get("/api/admin/force-resync-99")
def trigger_resync():
    from resync_tool import run_resync
    run_resync() # Triggers the logic
    return {"status": "Resync triggered. Check Render logs for details."}