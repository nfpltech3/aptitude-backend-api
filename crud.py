# crud.py
from sqlalchemy.orm import Session
from models import TestSession
from datetime import timedelta
from services.timer import get_ist_time

def get_session_by_token(db: Session, token: str):
    return db.query(TestSession).filter(TestSession.token == token).first()

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
