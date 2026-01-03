# services/grading.py
import string
from sqlalchemy.orm import Session
from models import Answer, TestSession
from services.grading_llm import get_llm_grade

def check_match(user_input: str, correct_answer: str) -> bool:
    """Helper: Normalizes text (lowercase, no punctuation) for flexible matching."""
    if not user_input or not correct_answer:
        return False

    # Lowercase & Strip
    u = str(user_input).lower().strip()
    c = str(correct_answer).lower().strip()

    # Remove Punctuation (Ignore dots, commas)
    u = u.translate(str.maketrans('', '', string.punctuation))
    c = c.translate(str.maketrans('', '', string.punctuation))

    u = " ".join(u.split())
    c = " ".join(c.split())
    
    return u == c

def calculate_score(session: TestSession, db: Session):
    print(f"\n--- 📝 START GRADING SESSION {session.id} ---")

    user_answers = db.query(Answer).filter(Answer.session_id == session.id).all() # query answer table for every rec belonging to that session id
    grading_key = session.grading_cache # correct answers
    
    total_score = 0
    total_possible = 0
    enriched_answers = []

    if not grading_key:
        return 0, [], 0
    
    # Create a lookup for user answers: {q_id: answer_text}
    user_ans_map = {str(ans.question_id): ans.answer_text for ans in user_answers}
    
    for q_id, q_data in grading_key.items():
        q_type = q_data.get("type")
        topic = q_data.get("topic", "General")
        max_marks = int(q_data.get("max_marks", 1))
        u_ans = user_ans_map.get(q_id, "")
        
        total_possible += max_marks
        current_q_score = 0
        status = "Wrong"

        # Skip Manual Grading for Long Answers
        if q_type == "Long Descriptive":
            status = "Manual"
        
        elif q_type == "MCQ":
            correct_letter = str(q_data.get("correct_mcq", "")).upper()
            if u_ans == correct_letter:
                current_q_score = max_marks
                status = "Correct"
                total_score += current_q_score
                    
        elif q_type == "Short Descriptive":
            correct_text_raw = str(q_data.get("correct_desc", ""))

            llm_score = get_llm_grade(u_ans, correct_text_raw, max_marks)
            if llm_score > 0:
                current_q_score = llm_score
                status = "Correct"
            else:
                # 2. Fallback to keyword matching
                possible = [x.strip() for x in correct_text_raw.split('|')]
                if any(check_match(u_ans, opt) for opt in possible):
                    current_q_score = max_marks
                    status = "Correct"
            
            total_score += current_q_score
            
        # Prepare for Zoho Transcript & Sectional calculation
        enriched_answers.append({
            "question_id": q_id,
            "topic": topic,
            "question_type": q_type,
            "answer_text": u_ans,
            "correct_answer": q_data.get("correct_mcq") if q_type=="MCQ" else q_data.get("correct_desc"),
            "marks_awarded": status if status == "Manual" else current_q_score,
            "max_marks": max_marks
        })
            
    print(f"--- 🏆 AUTOMATED SCORE: {total_score} ---\n")
    return total_score, enriched_answers, total_possible
