# resync_tool.py (FIXED VERSION)
from database import SessionLocal
from models import TestSession, Answer
from services.zoho_sync import update_candidate_summary
import json, time

def manual_resync():
    db = SessionLocal()
    try:
        # 1. Find sessions that are not synced
        unsynced_records = db.query(TestSession).filter(TestSession.is_synced == False).all()
        print(f"Found {len(unsynced_records)} records to sync...")

        for record in unsynced_records:
            print(f"Processing {record.candidate_name} (Session ID: {record.id})...")
            
            # 2. Fetch ACTUAL student answers from the Answer table
            student_answers = db.query(Answer).filter(Answer.session_id == record.id).all()
            
            # 3. Reconstruct the answers_list using the grading_cache
            # This matches the logic in your submit-test route
            q_front_map = {str(q["question_id"]): q for q in (record.question_cache or [])}
            q_grade_map = record.grading_cache or {}
            
            answers_payload = []
            for a in student_answers:
                q_id = str(a.question_id)
                q_data = q_front_map.get(q_id, {})
                q_grade_data = q_grade_map.get(q_id, {})

                # Determine correct answer and marks
                is_mcq = q_data.get("type") == "MCQ"
                correct_val = q_grade_data.get("correct_mcq") if is_mcq else q_grade_data.get("correct_desc")
                
                answers_payload.append({
                    "question_id": q_id,
                    "question_text": q_data.get("text", "Unknown"),
                    "question_type": q_data.get("type", "MCQ"),
                    "topic": q_data.get("topic", "General"),
                    "answer_text": a.answer_text,
                    "correct_answer": correct_val or "Not specified",
                    "marks_awarded": 0, # Note: You may want to call calculate_score here
                    "max_marks": q_grade_data.get("max_marks", 1)
                })

            # 4. Push to Zoho
            success = update_candidate_summary(
                zoho_id=record.candidate_id,
                mcq_score=record.total_score,
                status=record.status,
                scheduled_end_time=record.end_time,
                has_dept_test=record.has_department_test,
                total_possible_marks=100, 
                violations=record.violation_count,
                answers_list=answers_payload # Send the RECONSTRUCTED payload
            )

            if success:
                record.is_synced = True
                db.commit()
                print(f"Successfully synced {record.candidate_name}")
            
            time.sleep(1) # Rate limiting

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    manual_resync()