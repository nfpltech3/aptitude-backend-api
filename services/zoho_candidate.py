# zoho_candidate.py
import requests
import os
from services.zoho_auth import get_access_token, refresh_access_token # Import auth utils

def fetch_candidate_by_token(token: str):
    report_link_name = "API_Candidate_Data"
    owner = os.getenv("ZOHO_OWNER_NAME")
    app_link = os.getenv("ZOHO_APP_LINK")
    base_url = f"https://creator.zoho.in/api/v2/{owner}/{app_link}"
    
    url = f"{base_url}/report/{report_link_name}"
    
    params = {
        "criteria": f'(Unique_Token == "{token}")'
    }

    access_token = get_access_token()
    
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json"
    }

    # 4. Request with Error Handling
    try:
        response = requests.get(url, headers=headers, params=params)

        # --- RETRY LOGIC ---
        if response.status_code == 401:            
            new_token = refresh_access_token()
            headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
            response = requests.get(url, headers=headers, params=params)
        
        data = response.json()
        
        # Code 3000 = Success in Zoho
        if data.get("code") == 3000 and data.get("data"):
            return data["data"][0] 
        
        print(f"DEBUG: Data lookup failed. Code: {data.get('code')}")
        return None
        
    except Exception as e:
        print(f"Error fetching candidate: {e}")
        return None
