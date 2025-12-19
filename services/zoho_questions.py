# services/zoho_questions.py
import requests
import os
import time
from services.zoho_auth import get_access_token, refresh_access_token

BASE = "https://creator.zoho.in/api/v2"

_QUESTIONS_CACHE = []
_LAST_FETCH_TIME = 0
CACHE_DURATION = 3600

def fetch_all_zoho_questions():
    """
    Fetches ALL active questions from Zoho.
    Returns a raw list of dictionaries.
    """
    global _QUESTIONS_CACHE, _LAST_FETCH_TIME

    current_time = time.time()

    # 1. Return Cache if valid
    if _QUESTIONS_CACHE and (current_time - _LAST_FETCH_TIME < CACHE_DURATION):
        # print("✅ Using Cached Questions")
        return _QUESTIONS_CACHE

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
            _QUESTIONS_CACHE = data
            _LAST_FETCH_TIME = current_time
            print(f"✅ Cached {len(data)} questions.")
        
        return _QUESTIONS_CACHE

    except Exception as e:
        print(f"Error fetching questions: {e}")
        return []