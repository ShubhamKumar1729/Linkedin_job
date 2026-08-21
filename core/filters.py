import re
from utils.helpers import clean, normalize_email
from config.settings import (
    GMAIL_ID,
    CANDIDATE,
    CC_EMAILS,
    BCC_EMAILS,
    BAD_EMAIL_PREFIXES,
    BAD_EMAIL_DOMAINS,
    BENCHSALES_BLOCK_KEYWORDS,
    BENCHSALES_BLOCK_PATTERNS,
    JOB_REQUIREMENT_KEYWORDS,
)

# ── Posts to block completely ──────────────────────────────
BLOCK_POST_KEYWORDS = [
    # Training / coaching
    "training program",
    "certification program",
    "we help students",
    "upskill",
    "learn from",
    "enroll now",
    "batch starting",
    "online course",
    "job support",
    "interview preparation",
    "resume service",
    "career coaching",
    "job guarantee",
    "placement guarantee",
    "mentorship program",
    "demo class",
    "free webinar",

    # Not US jobs
    "bangalore",
    "hyderabad",
    "chennai",
    "mumbai",
    "india only",
    "pakistan",
    "latam",
    "mexico city",
    "saudi arabia",
    "ksa",

    # Not real hiring
    "comment interested",
    "comment \"interested\"",
    "send resume via dm",
    "send your cv via dm",
    "dm your resume",
    "dm me your resume",
    "whatsapp",
    "wa.me",
    "wa.link",
    "tag someone",

    # Freelance / gig
    "freelance network",
    "itfynder",
    "global freelance",
]

# ── Must have US signals ───────────────────────────────────
US_JOB_SIGNALS = [
    "w2",
    "c2c",
    "corp to corp",
    "usc",
    "us citizen",
    "green card",
    "ead",
    "opt",
    "stem opt",
    "h1b",
    "work authorization",
    "united states",
    " usa",
    "onsite",
    "remote",
    "hybrid",
]

# ── Must have email in post ────────────────────────────────
RECRUITER_EMAIL_SIGNALS = [
    "send resume",
    "send your resume",
    "share resume",
    "share your resume",
    "email resume",
    "apply",
    "reach out",
    "contact",
    "interested",
    "@",
]


def blocked_emails():
    """Own/copy-list addresses that must never become primary recipients."""
    blocked = {
        normalize_email(GMAIL_ID),
        normalize_email(CANDIDATE.get("email", "")),
    }
    blocked.update(normalize_email(email) for email in CC_EMAILS)
    blocked.update(normalize_email(email) for email in BCC_EMAILS)
    return {email for email in blocked if email}


def is_valid_recruiter_email(email):
    """Return True only if email looks like a real recruiter email."""
    email = normalize_email(email)
    if not email or "@" not in email:
        return False
    if email in blocked_emails():
        return False
    local, domain = email.rsplit("@", 1)
    if domain in BAD_EMAIL_DOMAINS:
        return False
    if domain.endswith((".example", ".invalid", ".test", ".localhost")):
        return False
    if local in BAD_EMAIL_PREFIXES:
        return False
    if len(local) <= 1:
        return False

    # Block personal gmail/yahoo unless looks recruiter-like
    personal_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com"}
    if domain in personal_domains:
        # Allow only if local part looks professional
        # Block obvious non-recruiters like random numbers
        if re.match(r"^[a-z]+\d{4,}@", email):
            return False

    return True


def filter_recruiter_emails(emails):
    """Filter list - return only valid unique recruiter emails."""
    valid = []
    seen  = set()
    for email in emails:
        email = normalize_email(email)
        if is_valid_recruiter_email(email) and email not in seen:
            seen.add(email)
            valid.append(email)
    return valid


def is_benchsales_post(post_text):
    """Return (True, reason) if post is bench sales."""
    low = clean(post_text).lower()
    for keyword in BENCHSALES_BLOCK_KEYWORDS:
        if keyword in low:
            return True, keyword
    for pattern in BENCHSALES_BLOCK_PATTERNS:
        if re.search(pattern, low, flags=re.IGNORECASE):
            return True, pattern
    return False, ""


def is_blocked_post(post_text):
    """Return (True, reason) if post should be blocked."""
    low = clean(post_text).lower()
    for keyword in BLOCK_POST_KEYWORDS:
        if keyword in low:
            return True, keyword
    return False, ""


def has_us_job_signal(post_text):
    """Return True if post has real US job signals."""
    low = clean(post_text).lower()
    return any(signal in low for signal in US_JOB_SIGNALS)


def looks_like_real_job(post_text):
    """Return True if post has real job hiring signals."""
    low = clean(post_text).lower()
    return any(kw in low for kw in JOB_REQUIREMENT_KEYWORDS)


def should_send_to_post(post_text):
    """
    Final gate - should we process this post?
    Returns (bool, reason_string)
    """
    # Check bench sales
    blocked, reason = is_benchsales_post(post_text)
    if blocked:
        return False, f"Bench Sales: {reason}"

    # Check blocked keywords
    blocked, reason = is_blocked_post(post_text)
    if blocked:
        return False, f"Blocked post: {reason}"

    # Must have job signal
    if not looks_like_real_job(post_text):
        return False, "No job signal found"

    # Must have US signal
    if not has_us_job_signal(post_text):
        return False, "No US job signal found"

    return True, "Valid US job post"