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

    user_answers = db.query(Answer).filter(Answer.session_id == session.id).all()
    grading_key = session.grading_cache 
    
    total_score = 0
    score_breakdown = {}

    if not grading_key:
        return 0, {} 
    
    for ans in user_answers:
        q_id = str(ans.question_id)
        u_ans = ans.answer_text
        current_q_score = 0
        is_correct = False
        
        if q_id in grading_key:
            q_data = grading_key[q_id]
            q_type = q_data.get("type")
            max_marks = int(q_data.get("max_marks", 1))

            # Skip Manual Grading for Long Answers
            if q_type == "Long Descriptive":
                score_breakdown[q_id] = "Manual"
                continue
                        
            if q_type == "MCQ":
                correct_opt = q_data.get("correct_mcq")
                if check_match(u_ans, correct_opt):
                    is_correct = True
                    current_q_score = max_marks
                    
            elif q_type == "Short Descriptive":
                correct_text_raw = str(q_data.get("correct_desc", ""))

                llm_score = get_llm_grade(u_ans, correct_text_raw, max_marks)
                if llm_score > 0:
                    is_correct = True
                    current_q_score = llm_score
                
                if not is_correct:
                    possible_answers = [x.strip() for x in correct_text_raw.split('|')]
                    for valid_opt in possible_answers:
                        if check_match(u_ans, valid_opt):
                            is_correct = True
                            current_q_score = max_marks
                            break
        
            # Assign Marks
            if is_correct:
                total_score += current_q_score
                print(f"   ✅ Q[{q_id}] Correct (+{current_q_score})")
            else:
                print(f"   ❌ Q[{q_id}] Wrong")

            score_breakdown[q_id] = current_q_score

    print(f"--- 🏆 AUTOMATED SCORE: {total_score} (Excluding Manual Questions) ---\n")
    return total_score, score_breakdown
