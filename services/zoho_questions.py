# services/zoho_questions.py
import json
import requests
import os
import time
from services.zoho_auth import get_access_token, refresh_access_token

BASE = "https://creator.zoho.in/api/v2"

CACHE_FILE = "questions_cache.json"
CACHE_DURATION = 86400 # 24 hours (Fetch once a day)

def fetch_all_zoho_questions():
    # 1. Try Loading from File First
    if os.path.exists(CACHE_FILE):
        file_age = time.time() - os.path.getmtime(CACHE_FILE)
        
        if file_age < CACHE_DURATION:
            # print("📂 Loading Questions from File (0 API Calls)")
            try:
                with open(CACHE_FILE, "r") as f:
                    return json.load(f)
            except:
                pass # If file is corrupted, fetch fresh

    current_time = time.time()

    url = f"{BASE}/{os.getenv('ZOHO_OWNER_NAME')}/{os.getenv('ZOHO_APP_LINK')}/report/Question_Master_Report"
    headers = {"Authorization": f"Zoho-oauthtoken {get_access_token()}"}
    params = {"criteria": '(Is_Active == "Yes")'}

    try:
        res = requests.get(url, headers=headers, params=params)

        # Token Refresh Logic
        if res.status_code == 401:
            print("Token expired. Refreshing...")
            new_token = refresh_access_token()
            headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
            res = requests.get(url, headers=headers, params=params)
        
        if res.status_code != 200:
            print(f"Zoho Error: {res.text}")
            return []

        # 3. Update Cache
        data = res.json().get("data", [])
        if data:
            with open(CACHE_FILE, "w") as f:
                json.dump(data, f)
                
        return data

    except Exception as e:
        print(f"Error fetching questions: {e}")
        return []