import time
import pandas as pd
from utils.helpers import normalize_email
from config.settings import SENT_FILE

_SENT_CACHE: set = set()
_SENT_EMAILS: set = set()


def load_sent_cache():
    global _SENT_CACHE, _SENT_EMAILS
    _SENT_CACHE = set()
    _SENT_EMAILS = set()

    if not SENT_FILE.exists():
        print("  No previous sent record found. Starting fresh.")
        return

    try:
        df = pd.read_csv(SENT_FILE)
        for _, row in df.iterrows():
            email = str(row["email"]).lower().strip()
            link = str(row["post_link"]).strip()
            _SENT_CACHE.add((email, link))
            if email:
                _SENT_EMAILS.add(email)
        print(
            f"  Loaded {len(_SENT_CACHE)} sent rows "
            f"({len(_SENT_EMAILS)} unique inboxes)."
        )
    except Exception as e:
        print(f"  Could not load sent cache: {e}")


def already_sent(email, post_link=""):
    """Skip if this inbox already received any submission."""
    email = normalize_email(email)
    if email in _SENT_EMAILS:
        return True
    key = (email, str(post_link).strip())
    return key in _SENT_CACHE


def save_sent(email, post_link, role_name):
    email = normalize_email(email)
    post_link = str(post_link).strip()

    _SENT_CACHE.add((email, post_link))
    _SENT_EMAILS.add(email)

    row = pd.DataFrame([{
        "email": email,
        "post_link": post_link,
        "role": role_name,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "SENT",
    }])

    if SENT_FILE.exists():
        try:
            old = pd.read_csv(SENT_FILE)
            row = pd.concat([old, row], ignore_index=True)
        except Exception:
            pass

    row.to_csv(SENT_FILE, index=False)
