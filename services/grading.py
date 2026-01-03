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
    
    q_meta_lookup = {str(q["question_id"]): q for q in session.question_cache}
    # Create a lookup for user answers: {q_id: answer_text}
    user_ans_map = {str(ans.question_id): str(ans.answer_text).strip() for ans in user_answers}
    
    for q_id, q_data in grading_key.items():
        q_type = q_data.get("type")
        topic = q_data.get("topic", "General")
        max_marks = int(q_data.get("max_marks", 1))
        
        # DISPLAY ANSWER: Original casing
        u_ans_display = user_ans_map.get(q_id, "")
        # COMPARISON ANSWER: Cleaned for logic
        u_ans_compare = str(u_ans_display).strip().upper()
        
        q_meta = q_meta_lookup.get(q_id, {})
        q_text = q_meta.get("text", f"Question {q_id}")
        
        total_possible += max_marks
        current_q_score = 0
        status = "Wrong"

        display_correct = ""
        display_student = u_ans_display
        
        # Skip Manual Grading for Long Answers
        if q_type == "Long Descriptive":
            status = "Manual"
        
        elif q_type == "MCQ":
            correct_letter = str(q_data.get("correct_mcq", "")).upper()
            letter_idx = ord(correct_letter) - 65
            options = q_meta.get("options", [])
            correct_text = options[letter_idx] if 0 <= letter_idx < len(options) else ""
            display_correct = f"({correct_letter}) {correct_text}"
            
            # If student answered, show their (Letter) + Text
            if u_ans_compare:
                student_idx = ord(u_ans_compare) - 65
                student_text = options[student_idx] if 0 <= student_idx < len(options) else "Invalid Option"
                display_student = f"({u_ans_compare}) {student_text}"

            if u_ans_compare == correct_letter:
                current_q_score = max_marks
                status = "Correct"
                total_score += current_q_score
                    
        elif q_type == "Short Descriptive":
            display_correct = q_data.get("correct_desc", "")

            llm_score = get_llm_grade(u_ans_display, display_correct, max_marks)
            if llm_score > 0:
                current_q_score = llm_score
                status = "Correct"
            elif any(check_match(u_ans_display, opt) for opt in str(display_correct).split('|')):
                current_q_score = max_marks
                status = "Correct"
            
            total_score += current_q_score
            
        # Prepare for Zoho Transcript & Sectional calculation
        enriched_answers.append({
            "question_id": q_id,
            "question_text": q_text,
            "topic": topic,
            "question_type": q_type,
            "answer_text": display_student,
            "correct_answer": display_correct,
            "marks_awarded": status if status == "Manual" else current_q_score,
            "max_marks": max_marks
        })
            
    print(f"--- 🏆 AUTOMATED SCORE: {total_score} ---\n")
    return total_score, enriched_answers, total_possible
