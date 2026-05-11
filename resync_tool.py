# resync_tool.py
from database import SessionLocal
from models import TestSession, Answer
from services.zoho_sync import update_candidate_summary
import json, time

def run_resync(target_zoho_id=None):
    db = SessionLocal()
    try:
        # 1. Query logic: Specific ID or all unsynced
        query = db.query(TestSession)
        if target_zoho_id:
            print(f"Targeting specific Zoho ID: {target_zoho_id}")
            query = query.filter(TestSession.candidate_id == str(target_zoho_id))
        else:
            print("Syncing all unsynced records...")
            query = query.filter(TestSession.is_synced == False)
        
        records = query.all()
        if not records:
            print("No records found to sync.")
            return

        for record in records:
            print(f"Processing: {record.candidate_name} (ID: {record.candidate_id})...")
            
            # 2. Fetch ACTUAL answers from the Answer table
            student_answers = db.query(Answer).filter(Answer.session_id == record.id).all()
            
            # 3. Reconstruct answers_list for the HTML transcript
            q_front_map = {str(q["question_id"]): q for q in (record.question_cache or [])}
            q_grade_map = record.grading_cache or {}
            
            answers_payload = []
            for a in student_answers:
                q_id = str(a.question_id)
                q_data = q_front_map.get(q_id, {})
                q_grade_data = q_grade_map.get(q_id, {})

                # Correct answer logic
                is_mcq = q_data.get("type") == "MCQ"
                correct_val = q_grade_data.get("correct_mcq") if is_mcq else q_grade_data.get("correct_desc")
                
                answers_payload.append({
                    "question_id": q_id,
                    "question_text": q_data.get("text", "Unknown"),
                    "question_type": q_data.get("type", "MCQ"),
                    "topic": q_data.get("topic", "General"),
                    "answer_text": a.answer_text,
                    "correct_answer": correct_val or "N/A",
                    "marks_awarded": a.marks_awarded, # Pulled from actual graded record in DB
                    "max_marks": q_grade_data.get("max_marks", 1)
                })

            # 4. BUG FIX: Map status to "Submitted" to avoid Zoho Validation Errors
            zoho_status = "Submitted" if record.status in ["Submitted", "Auto-Submitted"] else record.status

            # 5. Push to Zoho
            success = update_candidate_summary(
                zoho_id=record.candidate_id,
                mcq_score=record.total_score,
                status=zoho_status,
                start_time=str(record.start_time), # Pass as string
                scheduled_end_time=str(record.end_time), # Pass as string
                has_dept_test=record.has_department_test,
                total_possible_marks=100, # Adjust if needed
                violations=record.violation_count,
                answers_list=answers_payload,
                transcript_html=record.transcript_html
            )

            if success:
                record.is_synced = True
                db.commit()
                print(f"✅ Successfully synced {record.candidate_name}")
            
            time.sleep(1) # Safety delay

    except Exception as e:
        print(f"❌ Resync Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_resync(401134000000008241)