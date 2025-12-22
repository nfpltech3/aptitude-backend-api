# models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from database import Base
from services.timer import get_ist_time

question_cache = Column(JSON)
grading_cache = Column(JSON)

class TestSession(Base):
    __tablename__ = "test_sessions"

    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, index=True)
    candidate_id = Column(String)
    candidate_name = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String)  # In-Progress / Submitted / Auto-Submitted
    submission_type = Column(String, nullable=True)
    total_score = Column(Integer, default=0)
    submitted_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, default=40)
    position_name = Column(String, nullable=True)
    has_department_test = Column(String, default="No")
    
    question_cache = Column(JSON, nullable=True)
    grading_cache = Column(JSON, nullable=True)

class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("test_sessions.id"))
    question_id = Column(String)
    answer_text = Column(Text)
    saved_at = Column(DateTime, default=get_ist_time)
