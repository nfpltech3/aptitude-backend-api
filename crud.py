# crud.py
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from models import TestSession
from datetime import timedelta
from services.timer import get_ist_time

def get_session_by_token(db: Session, token: str):
    try:
        return db.query(TestSession).filter(TestSession.token == token).first()
    except OperationalError:
        # If the connection was closed (SSL error), SQLAlchemy pool_pre_ping 
        # usually handles it, but a manual rollback/retry ensures safety.
        db.rollback()
        return db.query(TestSession).filter(TestSession.token == token).first()

def create_placeholder_session(db: Session, token: str, zoho_id: str, duration_mins: int, position_name:str, has_dept_test: str, candidate_name: str):
    """Creates a session in 'Allocated' state without starting the timer."""
    existing = db.query(TestSession).filter(TestSession.token == token).first()
    if existing:
        return existing

    session = TestSession(
        token=token,
        candidate_id=zoho_id,
        candidate_name=candidate_name,
        start_time=None, 
        end_time=None,
        status="Allocated",
        submission_type="Pending",
        total_score=0,
        duration_minutes=duration_mins,
        position_name=position_name,
        has_department_test=has_dept_test
    )
    try:
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    except Exception as e:
        db.rollback()
        # Fallback in case of race condition: try fetching again
        return get_session_by_token(db, token)

def create_session(db: Session, token: str, zoho_id: str, duration_mins: int):
    now_ist = get_ist_time()
    # Use duration from Zoho (default to 40 if missing)
    duration = duration_mins if duration_mins else 40
    
    session = TestSession(
        token=token,
        candidate_id=zoho_id,
        start_time=now_ist,
        end_time=now_ist + timedelta(minutes=duration),
        status="In-Progress",
        total_score=0
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def start_session_timer(db: Session, session: TestSession, duration_mins: int):
    """Actually starts the timer for an Allocated session."""
    if session.status == "In-Progress":
        return session
    
    now_ist = get_ist_time()
    session.start_time = now_ist
    session.end_time = now_ist + timedelta(minutes=duration_mins)
    session.status = "In-Progress"

    db.commit()
    db.refresh(session)
    return session

def increment_violation(db: Session, session_id: int):
    session = db.query(models.TestSession).filter(models.TestSession.id == session_id).first()
    if session:
        session.violation_count += 1
        db.commit()
    return session.violation_count