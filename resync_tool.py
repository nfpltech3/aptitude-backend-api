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

        for record in unsynced_records:
            print(f"Syncing {record.candidate_name} (ID: {record.candidate_id})...")
            answers_data = record.grading_cache

            if isinstance(answers_data, str):
                answers_data = json.loads(answers_data)
            
            # 2. Call your existing sync function
            # Use the data already stored in your Neon database
            success = update_candidate_summary(
                zoho_id=record.candidate_id,
                mcq_score=record.total_score,
                status=record.status,
                scheduled_end_time=record.end_time,
                has_dept_test=record.has_department_test,
                total_possible_marks=100, # Adjust as per your logic
                violations=record.violation_count,
                answers_list=answers_data
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