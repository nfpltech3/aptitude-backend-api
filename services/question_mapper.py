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
        
        # --- 1. Construct Frontend Options ---
        # We explicitly fetch each option column
        opt_a = str(q.get("Option_A", "")).strip()
        opt_b = str(q.get("Option_B", "")).strip()
        opt_c = str(q.get("Option_C", "")).strip()
        opt_d = str(q.get("Option_D", "")).strip()

        # Build clean list for frontend
        options_list = [o for o in [opt_a, opt_b, opt_c, opt_d] if o]

        frontend_q = {
            "question_id": q_id,
            "text": q.get("Question_Text", ""), 
            "type": q_type,
            "options": options_list
        }
        safe_questions.append(frontend_q)

        # --- 2. Construct Grading Cache ---
        
        # A. Handle MCQ Mapping (The Code -> Text Fix)
        correct_val_raw = q.get("Correct_Answer") # This will be "A", "B", "C", "D"
        correct_mcq_text = None

        if correct_val_raw == "A":
            correct_mcq_text = opt_a
        elif correct_val_raw == "B":
            correct_mcq_text = opt_b
        elif correct_val_raw == "C":
            correct_mcq_text = opt_c
        elif correct_val_raw == "D":
            correct_mcq_text = opt_d
        else:
            # Fallback: Maybe they typed the full text in the correct answer field?
            correct_mcq_text = correct_val_raw

        # B. Handle Descriptive
        correct_desc = q.get("Correct_Descriptive_Answer2")

        grading_cache[q_id] = {
            "type": q_type,
            "topic": q.get("Topic", "General"),
            "max_marks": int(q.get("Max_Marks", 1) or 1), # Handle empty marks safely
            "correct_mcq": correct_mcq_text,  # Now stores "having been" instead of "A"
            "correct_desc": correct_desc
        }

    return safe_questions, grading_cache