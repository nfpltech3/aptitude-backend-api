# questions_mapper.py
import json

def sanitize_questions(raw_questions_list):
    """
    Transforms Zoho API response.
    Includes Logic to map 'A' -> 'Option A Text' for accurate grading.
    """
    safe_questions = []
    grading_cache = {}

    for q in raw_questions_list:
        q_id = str(q.get("ID"))
        q_type = q.get("Question_Type", "MCQ")
        
        # fetch each option column
        opt_a = str(q.get("Option_A", "")).strip()
        opt_b = str(q.get("Option_B", "")).strip()
        opt_c = str(q.get("Option_C", "")).strip()
        opt_d = str(q.get("Option_D", "")).strip()

        options_list = [o for o in [opt_a, opt_b, opt_c, opt_d] if o]

        frontend_q = {
            "question_id": q_id,
            "text": q.get("Question_Text", ""), 
            "type": q_type,
            "options": options_list
        }
        safe_questions.append(frontend_q)

        # Construct Grading Cache
        # Store the RAW letter (A, B, C, or D) for simple grading
        correct_val_raw = str(q.get("Correct_Answer", "")).strip().upper()

        grading_cache[q_id] = {
            "type": q_type,
            "topic": q.get("Topic", "General"),
            "max_marks": int(q.get("Max_Marks", 1) or 1),
            "correct_mcq": correct_val_raw,
            "correct_desc": q.get("Correct_Descriptive_Answer")
        }

    return safe_questions, grading_cache