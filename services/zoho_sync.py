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

def update_candidate_summary(zoho_id, mcq_score, status, scheduled_end_time, has_dept_test, total_possible_marks, violations, answers_list=None):
    """
    Updates Zoho with Score, Status, and a Topic-Wise HTML Transcript.
    """
    zoho_date_fmt = "%d-%b-%Y %H:%M:%S"
    actual_submission_time = get_ist_time().strftime(zoho_date_fmt)
    if isinstance(scheduled_end_time, str):
        # It's already a string, just use it
        deadline_time = scheduled_end_time
    else:
        # It's a datetime object, format it
        deadline_time = scheduled_end_time.strftime(zoho_date_fmt)

    # --- 1. CALCULATE SECTIONAL SCORES ---
    apt_total = 0
    num_total = 0
    vrb_total = 0
    dept_total = 0

    if answers_list:
        for ans in answers_list:
            topic = ans.get('topic', 'General')
                
            try:
                awarded = int(ans.get('marks_awarded', 0))
            except (ValueError, TypeError):
                awarded = 0
            
            if topic == "Aptitude":
                apt_total += awarded
            elif topic == "Numerical":
                num_total += awarded
            elif topic == "Verbal":
                vrb_total += awarded
            elif topic == "Departmental":
                dept_total += awarded
    
    # --- 2. PREPARE TRANSCRIPT HTML ---
    transcript_html = "<h3>📄 Candidate Test Transcript</h3>"
    current_topic = None
    
    if answers_list:
        for i, ans in enumerate(answers_list, 1):
            q_text = ans.get('question_text', 'Question ID: ' + str(ans['question_id']))
            ans_text = ans.get('answer_text', '')
            correct_ans = ans.get('correct_answer', 'N/A')
            q_type = ans.get('question_type', 'MCQ')
            topic = ans.get('topic', 'General')
            awarded = ans.get('marks_awarded', 0)
            max_marks = ans.get('max_marks', 1)

            if topic != current_topic:
                current_topic = topic
                transcript_html += f"""
                <div style='margin-top:20px; margin-bottom:10px; border-bottom:2px solid #007bff; padding-bottom:5px;'>
                    <h4 style='color:#007bff; margin:0;'>{current_topic} Section</h4>
                </div>
                """

            if awarded == "Manual":
                score_display = "<span style='color:orange; font-weight:bold;'>Pending Review</span>"
                bg_color = "#fffbf0" 
            else:
                score_display = f"<b>{awarded} / {max_marks}</b>"
                bg_color = "#e6fffa" if str(awarded) == str(max_marks) else "#fff5f5"

            # --- C. BUILD QUESTION CARD ---
            transcript_html += f"<div style='margin-bottom:15px; border:1px solid #eee; padding:10px; border-radius:5px;'>"
            
            transcript_html += f"<div style='display:flex; justify-content:space-between; margin-bottom:5px;'>"
            transcript_html += f"   <span style='font-weight:bold; color:#555;'>Q{i}: {q_type}</span>"
            transcript_html += f"   <span style='background:#eee; padding:2px 6px; border-radius:4px; font-size:12px;'>Marks: {score_display}</span>"
            transcript_html += f"</div>"
            transcript_html += f"<div style='margin-bottom:8px; color:#222; font-size:14px;'>{q_text}</div>"
            transcript_html += f"<div style='background-color:{bg_color}; padding:8px; border-left:3px solid #ccc; font-size:13px;'>"
            transcript_html += f"<b>Student Answer:</b> {ans_text}"
            transcript_html += "</div>"

            if str(awarded) != str(max_marks):
                transcript_html += f"<div style='background-color:#f0f7ff; padding:8px; border-left:3px solid #007bff; font-size:13px; color:#0056b3;'>"
                transcript_html += f"<b>Correct Answer:</b> {correct_ans}"
                transcript_html += "</div>"

            transcript_html += "</div>"
    else:
        transcript_html += "<p>No answers recorded.</p>"

    # --- 2. SEND TO ZOHO ---
    url = f"{BASE_URL}/report/Candidate_Allocation_Report/{zoho_id}"
    
    payload = {
        "data": {
            "Test_Status": status,
            "Total_Score": mcq_score,
            "Max_Possible_Marks": total_possible_marks,
            "Aptitude_Score": apt_total,
            "Numerical_Score": num_total,
            "Verbal_Score": vrb_total,
            "Dept_Score": dept_total if has_dept_test == "Yes" else None,
            "Proctoring_Violations": violations,
            "Suspicious_Activity": "Yes" if violations > 0 else "No",
            "Recruitment_Stage": "Test",
            "Token_Status": "Invalid",
            "Submitted_On": actual_submission_time,
            "Test_End_Time": deadline_time,
            "Test_Transcript": transcript_html 
        }
    }
    
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
    else:
        print(f"Success: Updated Candidate {zoho_id} with Score & Transcript.")


def push_candidate_answers(candidate_zoho_id, answers_list):
    # Target: The FORM (because we are creating NEW rows)
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
    
    # --- RETRY LOGIC ---
    if res.status_code == 401:
        print("Token expired during Answer Push. Refreshing...")
        new_token = refresh_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
        res = requests.post(url, headers=headers, json=payload)
            
    if res.status_code != 200:
        # Code 3000 means Success in Zoho V2 POST requests
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
    url = f"{BASE_URL}/report/Candidate_Allocation_Report/{zoho_id}"
    
    # Zoho Date Format: dd-MMM-yyyy HH:mm:ss
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
        
        # Retry logic if token expired
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
