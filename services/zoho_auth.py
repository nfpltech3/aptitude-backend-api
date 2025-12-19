import requests, os

def get_access_token():
    return os.getenv("ZOHO_ACCESS_TOKEN")

def refresh_access_token():
    url = "https://accounts.zoho.in/oauth/v2/token"
    params = {
        "grant_type": "refresh_token",
        "client_id": os.getenv("ZOHO_CLIENT_ID"),
        "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
        "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN")
    }

    res = requests.post(url, params=params)
    res.raise_for_status()

    new_token = res.json()["access_token"]
    os.environ["ZOHO_ACCESS_TOKEN"] = new_token
    return new_token
