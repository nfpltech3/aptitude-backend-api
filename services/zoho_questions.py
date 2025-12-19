# services/zoho_questions.py
import requests
import os
from services.zoho_auth import get_access_token, refresh_access_token

BASE = "https://creator.zoho.in/api/v2"

def fetch_all_zoho_questions():
    """
    Fetches ALL active questions from Zoho.
    Returns a raw list of dictionaries.
    """
    url = f"{BASE}/{os.getenv('ZOHO_OWNER_NAME')}/{os.getenv('ZOHO_APP_LINK')}/report/Question_Master_Report"
    headers = {"Authorization": f"Zoho-oauthtoken {get_access_token()}"}
    
    # Only get Active questions
    params = {"criteria": '(Is_Active == "Yes")'}

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

    return res.json().get("data", [])