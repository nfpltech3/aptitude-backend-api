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
    total_possible = 0
    enriched_answers = []

    if not grading_key:
        return 0, [], 0
    
    # Create a lookup for user answers: {q_id: answer_text}
    user_ans_map = {str(ans.question_id): ans.answer_text for ans in user_answers}
    
    # Calculate total marks possible
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
            current_q_score = 0  # Not auto-graded
            status = "Manual"
        
        elif q_type == "MCQ":
            # Mapper stores the FULL TEXT in correct_mcq
            correct_text = q_data.get("correct_mcq")
            if check_match(u_ans, correct_text):
                current_q_score = max_marks
                status = "Correct"
                total_score += current_q_score
                        
            if q_type == "MCQ":
                correct_letter = q_data.get("correct_mcq")

                if str(u_ans).strip().upper() == str(correct_letter).strip().upper():
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
    return total_score, score_breakdown, total_possible
