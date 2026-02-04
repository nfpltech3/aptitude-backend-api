from pydantic import BaseModel, field_validator
from typing import List, Optional

class StartTestResponse(BaseModel):
    end_time: str
    questions: list

class SaveAnswerRequest(BaseModel):
    token: str
    question_id: str
    answer_text: str
    client_timestamp: Optional[float] = None  # Unix timestamp (ms) when user clicked

    @field_validator('question_id') 
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError('Question ID must be a numeric string')
        return v

class SubmitRequest(BaseModel):
    token: str
