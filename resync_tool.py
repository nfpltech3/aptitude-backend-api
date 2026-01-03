# resync_tool.py
from database import SessionLocal
from models import TestSession
from services.zoho_sync import update_candidate_summary
import time
import json

def manual_resync():
    db = SessionLocal()
    try:
        # 1. Fetch all records that haven't been synced yet
        unsynced_records = db.query(TestSession).filter(TestSession.is_synced == False).all()
        
        print(f"Found {len(unsynced_records)} records to sync...")

        # resync_tool.py (Updated Logic)
        for record in unsynced_records:
            print(f"Syncing {record.candidate_name} (ID: {record.candidate_id})...")
            
            answers_data = record.grading_cache

            # 1. Handle double-encoding or raw strings
            if isinstance(answers_data, str):
                try:
                    answers_data = json.loads(answers_data)
                    # If it's STILL a string after one load, load it again (double-encoded)
                    if isinstance(answers_data, str):
                        answers_data = json.loads(answers_data)
                except Exception:
                    answers_data = [] # Fallback to empty list if corrupted

            # 2. Safety check: ensure every item in the list is a dictionary
            clean_answers = []
            if isinstance(answers_data, list):
                for item in answers_data:
                    if isinstance(item, str):
                        try:
                            clean_answers.append(json.loads(item))
                        except: continue
                    else:
                        clean_answers.append(item)
            
            # 3. Call sync function with the clean list
            success = update_candidate_summary(
                zoho_id=record.candidate_id,
                mcq_score=record.total_score,
                status=record.status,
                scheduled_end_time=record.end_time,
                has_dept_test=record.has_department_test,
                total_possible_marks=100,
                violations=record.violation_count,
                answers_list=clean_answers # Use the cleaned list
            )

            if success:
                # 3. Update the flag so it doesn't sync again
                record.is_synced = True
                db.commit()
                print(f"Successfully synced {record.candidate_name}")
            else:
                print(f"Failed to sync {record.candidate_name}. Check Zoho report name.")
            
            # Small delay to avoid Zoho API rate limits
            time.sleep(1) 

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    manual_resync()