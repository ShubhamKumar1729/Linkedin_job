import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _env_int(name, default, minimum=None, maximum=None):
    """Read and validate an integer environment setting."""
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw_value!r}") from exc

    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


# ── Paths ──────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

SENT_FILE    = OUTPUT_DIR / "sent_emails.csv"
PROFILE_DIR  = str(BASE_DIR / "linkedin_profile_data")

RESUME_FILENAME = os.getenv("RESUME_FILENAME", "resume.pdf").strip()
RESUME_PATH     = OUTPUT_DIR / RESUME_FILENAME

# ── Gmail Credentials ──────────────────────────────────────
GMAIL_ID           = os.getenv("GMAIL_ID", "").strip()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()

# ── Groq AI ────────────────────────────────────────────────
GROQ_API_KEY             = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL               = os.getenv(
    "GROQ_MODEL", "openai/gpt-oss-120b"
).strip()
AI_RELEVANCE_THRESHOLD   = _env_int(
    "AI_RELEVANCE_THRESHOLD", 70, minimum=0, maximum=100
)
AI_MATCH_MODE            = os.getenv(
    "AI_MATCH_MODE", "role_location"
).strip().lower()
if AI_MATCH_MODE not in {"role_location", "strict"}:
    raise ValueError("AI_MATCH_MODE must be 'role_location' or 'strict'")
GROQ_TIMEOUT_SECONDS     = _env_int(
    "GROQ_TIMEOUT_SECONDS", 30, minimum=1
)
GROQ_MAX_RETRIES         = _env_int(
    "GROQ_MAX_RETRIES", 2, minimum=0, maximum=5
)
GROQ_MAX_COMPLETION_TOKENS = _env_int(
    "GROQ_MAX_COMPLETION_TOKENS", 1000, minimum=300
)
DELAY_BETWEEN_AI_REQUESTS = _env_int(
    "DELAY_BETWEEN_AI_REQUESTS", 15, minimum=0
)
GROQ_RATE_LIMIT_COOLDOWN_SECONDS = _env_int(
    "GROQ_RATE_LIMIT_COOLDOWN_SECONDS", 60, minimum=1
)
GROQ_MAX_RATE_LIMIT_WAIT_SECONDS = _env_int(
    "GROQ_MAX_RATE_LIMIT_WAIT_SECONDS", 300, minimum=1
)

# ── Candidate Info ─────────────────────────────────────────
CANDIDATE = {
    "name":         os.getenv("CANDIDATE_NAME",         "").strip(),
    "email":        os.getenv("CANDIDATE_EMAIL",        "").strip(),
    "phone":        os.getenv("CANDIDATE_PHONE",        "").strip(),
    "linkedin":     os.getenv("CANDIDATE_LINKEDIN",     "").strip(),
    "location":     os.getenv("CANDIDATE_LOCATION",     "").strip(),
    "relocation":   os.getenv("CANDIDATE_RELOCATION",   "").strip(),
    "work_auth":    os.getenv("CANDIDATE_WORK_AUTH",    "").strip(),
    "availability": os.getenv("CANDIDATE_AVAILABILITY", "").strip(),
    "experience":   os.getenv("CANDIDATE_EXPERIENCE",   "").strip(),
    "rate":         os.getenv("CANDIDATE_RATE",         "").strip(),
}
MAX_EXPERIENCE_YEARS = _env_int(
    "MAX_EXPERIENCE_YEARS", 5, minimum=0, maximum=50
)

# ── CC / BCC ───────────────────────────────────────────────
def _parse_list(key):
    raw = os.getenv(key, "").strip()
    if not raw:
        return []
    return [e.strip() for e in raw.split(",") if e.strip()]

CC_EMAILS  = _parse_list("CC_EMAILS")
BCC_EMAILS = _parse_list("BCC_EMAILS")

# ── Bot Settings ───────────────────────────────────────────
# MAX_EMAILS_PER_ROLE is accepted as a backwards-compatible fallback.
_legacy_email_limit      = os.getenv("MAX_EMAILS_PER_ROLE", "100")
MAX_EMAILS_PER_RUN       = _env_int(
    "MAX_EMAILS_PER_RUN", _legacy_email_limit, minimum=1
)
# TARGET_EMAILS_PER_ROLE remains a backwards-compatible fallback. This is a
# minimum reporting goal, not a cap; quality sends continue up to the run limit.
_legacy_role_target      = os.getenv("TARGET_EMAILS_PER_ROLE", "3")
MIN_QUALITY_EMAILS_PER_ROLE = _env_int(
    "MIN_QUALITY_EMAILS_PER_ROLE", _legacy_role_target, minimum=1
)
MAX_PASSES_PER_ROLE      = _env_int(
    "MAX_PASSES_PER_ROLE", 3, minimum=1, maximum=20
)
MAX_EMAILS_PER_POST      = _env_int("MAX_EMAILS_PER_POST", 5, minimum=1)
MAX_JOB_DESCRIPTION_CHARS = _env_int(
    "MAX_JOB_DESCRIPTION_CHARS", 12000, minimum=1000
)
DELAY_BETWEEN_EMAILS     = _env_int("DELAY_BETWEEN_EMAILS", 12, minimum=0)
SCROLL_ROUNDS            = _env_int("SCROLL_ROUNDS", 8, minimum=0)
WAIT_BETWEEN_ROLES_MIN   = _env_int(
    "WAIT_BETWEEN_ROLES_MIN", 60, minimum=0
)
WAIT_BETWEEN_ROLES_MAX   = _env_int(
    "WAIT_BETWEEN_ROLES_MAX", 120, minimum=0
)

if WAIT_BETWEEN_ROLES_MAX < WAIT_BETWEEN_ROLES_MIN:
    raise ValueError(
        "WAIT_BETWEEN_ROLES_MAX must be greater than or equal to "
        "WAIT_BETWEEN_ROLES_MIN"
    )

# ── Email Filtering ────────────────────────────────────────
BAD_EMAIL_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "admin", "support", "help", "info", "contact",
    "sales", "marketing", "privacy", "security",
    "abuse", "postmaster", "mailer-daemon",
}

BAD_EMAIL_DOMAINS = {
    "linkedin.com",
    "example.com",
    "test.com",
}

# ── Bench Sales Block ──────────────────────────────────────
BENCHSALES_BLOCK_KEYWORDS = [
    "bench sales",
    "benchsales",
    "bench-sale",
    "bench_sale",
    "benchsales recruiter",
    "bench sales recruiter",
]

BENCHSALES_BLOCK_PATTERNS = [
    r"\bbench\s*sales\b",
    r"\bbench[-_\s]*sales\b",
    r"\bbenchsales\b",
]

# ── Job Signal Keywords ────────────────────────────────────
JOB_REQUIREMENT_KEYWORDS = [
    "hiring", "we are hiring", "now hiring",
    "job opening", "opening", "open role",
    "requirement", "urgent requirement",
    "position", "role", "opportunity",
    "looking for", "need", "needed", "required",
    "contract", "fulltime", "full time",
    "w2", "c2c", "onsite", "remote", "hybrid",
    "job description", "jd",
    "data operations", "data analyst", "data engineer",
    "business analyst", "project coordinator",
    "system analyst", "scrum master", "iam analyst",
    "etl", "azure", "sql", "cloud", "agile", "scrum",
]

# ── Load Roles From .env ───────────────────────────────────
def load_roles():
    roles = []
    i = 1
    while True:
        name   = os.getenv(f"ROLE_{i}_NAME",   "").strip()
        skills = os.getenv(f"ROLE_{i}_SKILLS", "").strip()
        search = os.getenv(f"ROLE_{i}_SEARCH", "").strip()
        if not name:
            break
        roles.append({
            "index":  i,
            "name":   name,
            "skills": skills,
            "search": search,
        })
        i += 1
    return roles

ROLES = load_roles()