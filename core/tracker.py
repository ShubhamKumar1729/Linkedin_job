import time
import pandas as pd
from utils.helpers import normalize_email
from config.settings import SENT_FILE

# In-memory cache - loaded once at startup
_SENT_CACHE: set = set()


def load_sent_cache():
    """Load all previously sent records into memory."""
    global _SENT_CACHE
    _SENT_CACHE = set()

    if not SENT_FILE.exists():
        print("  No previous sent record found. Starting fresh.")
        return

    try:
        df = pd.read_csv(SENT_FILE)
        for _, row in df.iterrows():
            key = (
                str(row["email"]).lower().strip(),
                str(row["post_link"]).strip(),
            )
            _SENT_CACHE.add(key)
        print(f"  Loaded {len(_SENT_CACHE)} previously sent records.")
    except Exception as e:
        print(f"  Could not load sent cache: {e}")


def already_sent(email, post_link):
    """Check memory cache - fast O(1) lookup."""
    key = (normalize_email(email), str(post_link).strip())
    return key in _SENT_CACHE


def save_sent(email, post_link, role_name):
    """Save sent record to CSV and add to memory cache."""
    email     = normalize_email(email)
    post_link = str(post_link).strip()

    # Add to memory cache immediately
    _SENT_CACHE.add((email, post_link))

    row = pd.DataFrame([{
        "email":     email,
        "post_link": post_link,
        "role":      role_name,
        "time":      time.strftime("%Y-%m-%d %H:%M:%S"),
        "status":    "SENT",
    }])

    if SENT_FILE.exists():
        try:
            old = pd.read_csv(SENT_FILE)
            row = pd.concat([old, row], ignore_index=True)
        except Exception:
            pass

    row.to_csv(SENT_FILE, index=False)