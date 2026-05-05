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

            llm_result = get_llm_grade(u_ans_display, display_correct, max_marks)
            # print(f"DEBUG: llm_result type is {type(llm_result)} and value is {llm_result}")
            llm_score = llm_result.get("score", 0)
            llm_reason = llm_result.get("reason", "")
            
            if llm_score > 0:
                current_q_score = llm_score
                status = "Correct"
            elif any(check_match(u_ans_display, opt) for opt in str(display_correct).split('|')):
                current_q_score = max_marks
                status = "Correct"
                llm_reason = "Exact match found in reference options."
            
            total_score += current_q_score
        
        db_answer = db.query(Answer).filter(
            Answer.session_id == session.id, 
            Answer.question_id == q_id
        ).first()

        if db_answer:
            # Update the physical columns in the database
            db_answer.marks_awarded = str(status if status == "Manual" else current_q_score)
            db_answer.grading_reason = llm_reason if q_type == "Short Descriptive" else "Standard MCQ Logic"

        # Prepare for Zoho Transcript & Sectional calculation
        enriched_answers.append({
            "question_id": q_id,
            "question_text": q_text,
            "topic": topic,
            "question_type": q_type,
            "answer_text": display_student,
            "correct_answer": display_correct,
            "marks_awarded": status if status == "Manual" else current_q_score,
            "max_marks": max_marks,
            "grading_reason": llm_reason if q_type == "Short Descriptive" else "Standard MCQ Logic"
        })

    db.commit() 
    print(f"--- 🏆 AUTOMATED SCORE: {total_score} ---\n")
    return total_score, enriched_answers, total_possible


def generate_transcript_html(answers_list):
    if not answers_list:
        return "<p>No answers recorded.</p>"

    # Sectional aggregation
    sectional_data = {}
    for ans in answers_list:
        topic = ans.get('topic', 'General')
        max_q = int(ans.get('max_marks', 0))
        raw_awarded = ans.get('marks_awarded', 0)
        is_manual = (raw_awarded == "Manual")
        awarded_val = int(raw_awarded) if str(raw_awarded).isdigit() else 0

        if topic not in sectional_data:
            sectional_data[topic] = {"auto_awarded": 0, "auto_max": 0, "manual_max": 0}

        if is_manual:
            sectional_data[topic]["manual_max"] += max_q
        else:
            sectional_data[topic]["auto_awarded"] += awarded_val
            sectional_data[topic]["auto_max"] += max_q

    # Build HTML
    transcript_priority = {"Departmental": 0, "Numerical": 1, "Verbal": 2}
    transcript_html = "<h3>Assessment Performance Summary</h3>"
    current_topic = None

    answers_list.sort(key=lambda x: transcript_priority.get(x.get('topic', 'General'), 99))

    for i, ans in enumerate(answers_list, 1):
        topic = ans.get('topic', 'General')
        sec_score = sectional_data.get(topic)

        if topic != current_topic:
            current_topic = topic
            if sec_score["manual_max"] > 0:
                score_display = f"{sec_score['auto_awarded']}/{sec_score['auto_max']} (Auto) | {sec_score['manual_max']} pending"
            else:
                score_display = f"{sec_score['auto_awarded']}/{sec_score['auto_max']}"
            transcript_html += f"<div style='margin:10px 0;border-bottom:2px solid #007bff;padding:3px'>"
            transcript_html += f"<b style='color:#007bff'>{current_topic}</b> ({score_display})</div>"

        q_text = ans.get('question_text', f'Q-{ans["question_id"]}')
        ans_text = ans.get('answer_text', '-')
        correct_ans = ans.get('correct_answer', '')
        awarded = ans.get('marks_awarded', 0)
        max_marks = ans.get('max_marks', 1)

        color = "orange" if awarded == "Manual" else ("green" if str(awarded) == str(max_marks) else "red")

        transcript_html += f"<div style='margin:5px 0;padding:8px;border:1px solid #ddd'>"
        transcript_html += f"<b>Q{i}</b> <span style='color:{color}'>[{awarded}/{max_marks}]</span><br>"
        transcript_html += f"{q_text}<br><b>Ans:</b> {ans_text}"
        if str(awarded) != str(max_marks) and awarded != "Manual":
            transcript_html += f"<br><span style='color:#007bff'><b>Correct:</b> {correct_ans}</span>"
        transcript_html += "</div>"

    return transcript_html
