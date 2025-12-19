# services/timer.py
from datetime import datetime
import pytz

def get_ist_time():
    """Returns current time shifted to IST (UTC + 5:30)"""
    ist_zone = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist_zone).replace(tzinfo=None)

def is_time_over(session):
    # Compare session end time with current IST time
    return get_ist_time() > session.end_time