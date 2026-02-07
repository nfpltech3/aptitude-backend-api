# services/zoho_sync.py
import requests
import os
from datetime import datetime
from services.zoho_auth import get_access_token, refresh_access_token
from dotenv import load_dotenv
from services.timer import get_ist_time
load_dotenv()

# 1. Base Configuration
ZOHO_OWNER = os.getenv("ZOHO_OWNER_NAME")
ZOHO_APP = os.getenv("ZOHO_APP_LINK")
BASE_URL = f"https://creator.zoho.in/api/v2/{ZOHO_OWNER}/{ZOHO_APP}"

# 2. Header Generator
def get_headers():
    """Generates headers with the current Access Token from env"""
    token = get_access_token()
    return {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json"
    }

def update_candidate_summary(zoho_id, mcq_score, status, start_time, scheduled_end_time, has_dept_test, total_possible_marks, violations, answers_list=None):
    """
    Updates Zoho with Score, Status, and a Topic-Wise HTML Transcript.
    """
    zoho_date_fmt = "%d-%b-%Y %H:%M:%S"
    
    actual_submission_time = get_ist_time().strftime(zoho_date_fmt)
    start_time_str = start_time.strftime(zoho_date_fmt) if start_time else ""
    if isinstance(scheduled_end_time, str):
        # It's already a string, just use it
        deadline_time = scheduled_end_time
    else:
        # It's a datetime object, format it
        deadline_time = scheduled_end_time.strftime(zoho_date_fmt)

    # --- 1. DYNAMIC SECTIONAL AGGREGATION ---
    # This dictionary will store: {"Topic Name": {"awarded": X, "max": Y}}
    sectional_data = {}
    calculated_total = 0
    filtered_max_marks = 0

    if answers_list:
        for ans in answers_list:
            topic = ans.get('topic', 'General')
            max_q = int(ans.get('max_marks', 0))
            
            # Logic: If 'Manual', awarded points for calculation is 0
            raw_awarded = ans.get('marks_awarded', 0)
            awarded_val = int(raw_awarded) if str(raw_awarded).isdigit() else 0

            if topic not in sectional_data:
                sectional_data[topic] = {"awarded": 0, "max": 0}
            
            sectional_data[topic]["awarded"] += awarded_val
            sectional_data[topic]["max"] += max_q

            if topic != "Departmental":
                calculated_total += awarded_val
                filtered_max_marks += max_q
    
    # --- 2. PREPARE TRANSCRIPT HTML (Compact Version for Zoho Limit) ---
    transcript_priority = {"Departmental": 0, "Numerical": 1, "Verbal": 2}
    transcript_html = "<h3>Assessment Performance Summary</h3>"
    current_topic = None
    
    if answers_list:
        answers_list.sort(key=lambda x: transcript_priority.get(x.get('topic', 'General'), 99))
        for i, ans in enumerate(answers_list, 1):
            topic = ans.get('topic', 'General')
            sec_score = sectional_data.get(topic, {"awarded": 0, "max": 0})
            
            # Section Header (only when topic changes)
            if topic != current_topic:
                current_topic = topic
                transcript_html += f"<div style='margin:15px 0;border-bottom:2px solid #007bff;padding:5px 0;'>"
                transcript_html += f"<b style='color:#007bff;'>{current_topic} Section</b> "
                transcript_html += f"<span style='background:#007bff;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;'>"
                transcript_html += f"{sec_score['awarded']}/{sec_score['max']}</span></div>"
            
            q_text = ans.get('question_text', f'Q-{ans["question_id"]}')  # Full question text, no truncation
            ans_text = ans.get('answer_text', '-')  # Full answer text
            correct_ans = ans.get('correct_answer', '')  # Full correct answer
            q_type = ans.get('question_type', 'MCQ')
            awarded = ans.get('marks_awarded', 0)
            max_marks = ans.get('max_marks', 1)
            
            # Determine styling
            if awarded == "Manual":
                mark_style = "color:orange;"
                mark_text = "Pending"
            elif str(awarded) == str(max_marks):
                mark_style = "color:green;"
                mark_text = f"{awarded}/{max_marks}"
            else:
                mark_style = "color:red;"
                mark_text = f"{awarded}/{max_marks}"
            
            # Compact Question Card
            transcript_html += f"<div style='margin:8px 0;padding:8px;border:1px solid #ddd;border-radius:4px;'>"
            transcript_html += f"<b>Q{i}</b> [{q_type}] <span style='{mark_style}font-weight:bold;'>{mark_text}</span><br>"
            transcript_html += f"<span style='color:#333;'>{q_text}</span><br>"
            transcript_html += f"<span style='color:#666;'>Ans: {ans_text}</span>"
            
            # Show correct answer only if wrong (non-departmental)
            if topic != "Departmental" and str(awarded) != str(max_marks) and awarded != "Manual":
                transcript_html += f"<br><span style='color:#007bff;'>Correct: {correct_ans}</span>"
            
            transcript_html += "</div>"
    else:
        transcript_html += "<p>No answers recorded.</p>"
    
    # Safety check: Zoho has ~32000 char limit, truncate if needed
    ZOHO_CHAR_LIMIT = 31000
    if len(transcript_html) > ZOHO_CHAR_LIMIT:
        transcript_html = transcript_html[:ZOHO_CHAR_LIMIT] + "...<p><b>⚠️ Transcript truncated due to length.</b></p>"
        print(f"⚠️ Transcript exceeded {ZOHO_CHAR_LIMIT} chars, truncated.")

    # --- 2. SEND TO ZOHO ---
    url = f"{BASE_URL}/report/All_Candidate_Assessments/{zoho_id}"
    
    payload_data = {
        "Test_Status": status,
        "Total_Score": str(calculated_total),
        "Max_Possible_Marks": str(filtered_max_marks),
        "Proctoring_Violations": violations,
        "Suspicious_Activity": "Yes" if violations > 0 else "No",
        "Token_Status": "Used",
        "Submitted_On": actual_submission_time,
        "Test_Start_Time": start_time_str,
        "Test_End_Time": deadline_time,
        "Test_Transcript": transcript_html 
    }
    
    # Map the dictionary values back to Zoho fields
    # Note: Ensure your Zoho field names stay consistent (e.g., 'Numerical_Score')
    for topic, scores in sectional_data.items():
        if topic == "Departmental":
            continue
        field_name = f"{topic.replace(' ', '_')}_Score"
        payload_data[field_name] = f"{scores['awarded']} / {scores['max']}"
    
    payload = {"data": payload_data}
    
    headers = get_headers()
    res = requests.patch(url, headers=headers, json=payload)
    
    # Retry Logic
    if res.status_code == 401:
        print("Token expired. Refreshing...")
        new_token = refresh_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
        res = requests.patch(url, headers=headers, json=payload)
            
    if res.status_code != 200:
        print(f"Error updating Summary: {res.text}")
        return False
    else:
        resp_data = res.json()
        if resp_data.get("code") == 3000:
            print(f"Success: Updated Candidate {zoho_id}")
            return True # Explicitly return True so resync_tool knows it worked
        else:
            print(f"Zoho Error Code: {resp_data.get('code')}")
            return False

def push_candidate_answers(candidate_zoho_id, answers_list):
    form_link_name = "Candidate_Test_Form"
    
    url = f"{BASE_URL}/form/{form_link_name}"
    
    # Prepare a list of rows to add
    records = []
    for ans in answers_list:
        records.append({
            "Candidate_Lookup": candidate_zoho_id,
            "Question_Lookup": ans["question_id"], 
            "Student_Answer": ans["answer_text"]
        })
    
    payload = {"data": records}
    
    # Send Request
    headers = get_headers()
    res = requests.post(url, headers=headers, json=payload)
    
    if res.status_code == 401:
        print("Token expired during Answer Push. Refreshing...")
        new_token = refresh_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
        res = requests.post(url, headers=headers, json=payload)
            
    if res.status_code != 200:
        response_json = res.json()
        if response_json.get("code") == 3000:
            print(f"Success: Pushed {len(records)} answers.")
        else:
            print(f"Error pushing answers: {res.text}")
    else:
         print(f"Success: Pushed {len(records)} answers.")

def mark_test_started(zoho_id):
    """
    Updates Zoho with the Start Time and changes Status to 'In Progress'.
    """
    url = f"{BASE_URL}/report/All_Candidate_Assessments/{zoho_id}"
    
    start_time_str = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
    
    payload = {
        "data": {
            "Test_Start_Time": start_time_str,
            "Test_Status": "Started"
        }
    }
    
    headers = get_headers()
    try:
        res = requests.patch(url, headers=headers, json=payload)
        
        if res.status_code == 401:
            new_token = refresh_access_token()
            headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
            res = requests.patch(url, headers=headers, json=payload)
            
        if res.status_code == 200:
            print(f"Success: Synced Start Time for ID {zoho_id}")
        else:
            print(f"DEBUG: Start Time Update Failed! Status: {res.status_code}")
            print(f"DEBUG: Zoho Response: {res.text}")
            
    except Exception as e:
        print(f"Zoho Sync Error (Start Time): {e}")
