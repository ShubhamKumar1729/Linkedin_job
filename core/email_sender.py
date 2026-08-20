import time
import re
import yagmail

from utils.helpers import normalize_email, normalize_post_link, clean
from core.tracker import already_sent, save_sent
from core.filters import blocked_emails
from config.settings import (
    GMAIL_ID,
    GMAIL_APP_PASSWORD,
    CANDIDATE,
    CC_EMAILS,
    BCC_EMAILS,
    DELAY_BETWEEN_EMAILS,
)


def extract_clean_jd(post_text):
    """
    Extract only the job description part.
    Removes LinkedIn UI junk and limits length.
    """
    junk_lines = {
        "like", "comment", "repost", "send", "feed post",
        "follow", "connect", "join", "more",
        "are these results helpful",
        "your feedback helps us improve search results",
        "linkedin corporation © 2026",
        "linkedin corporation",
        "privacy & terms", "help center", "accessibility",
        "about", "ad choices", "advertising",
        "business services", "get the linkedin app",
        "• 3rd+", "• 2nd", "• 1st",
        "visit my website", "subscribe",
    }

    lines = post_text.split("\n")
    clean_lines = []

    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        low = line.lower()

        # Skip exact junk matches
        if low in junk_lines:
            continue

        # Skip reaction/comment counts like "7 reactions"
        if re.match(r"^\d+\s*(reaction|comment|repost)", low):
            continue

        # Skip timestamps like "21m •", "1h •"
        if re.match(r"^\d+[mh]\s*[•·]?", line):
            continue

        # Skip lines that are just numbers
        if re.match(r"^\d+$", line):
            continue

        clean_lines.append(line)

    cleaned = "\n".join(clean_lines)

    # Limit to 600 chars
    if len(cleaned) > 600:
        cleaned = cleaned[:600].rsplit("\n", 1)[0] + "\n..."

    return cleaned.strip()


def build_email_body(role, post_text, post_link, recruiter_name=""):
    """Build plain text email body with clean JD."""

    greeting = (
        f"Dear {recruiter_name},"
        if recruiter_name
        else "Dear Hiring Manager,"
    )

    clean_jd = extract_clean_jd(post_text)

    body = f"""{greeting}

I came across your posting for a {role['name']} position. My hands-on experience with {role['skills']} maps directly to what you are looking for, and I would welcome the opportunity to be considered.

Please find my submission details below for your review:

--- SUBMISSION DETAILS ---
\u2022 Candidate Name:      {CANDIDATE['name']}
\u2022 Applied Role:        {role['name']}
\u2022 Total Experience:    {CANDIDATE['experience']}
\u2022 Phone / Contact:     {CANDIDATE['phone']}
\u2022 Email Address:       {CANDIDATE['email']}
\u2022 Current Location:    {CANDIDATE['location']}
\u2022 Relocation:          {CANDIDATE['relocation']}
\u2022 Work Authorization:  {CANDIDATE['work_auth']}
\u2022 Availability:        {CANDIDATE['availability']}
\u2022 Rate / Compensation: {CANDIDATE['rate']}
\u2022 LinkedIn Profile:    {CANDIDATE['linkedin']}

I have attached my updated resume for your review. Are you available for a brief call sometime this week to discuss this position? Thank you for your time and consideration; I look forward to hearing from you.

Best regards,
{CANDIDATE['name']}
Phone: {CANDIDATE['phone']} | Email: {CANDIDATE['email']}
LinkedIn: {CANDIDATE['linkedin']}


FOR REFERENCE

{clean_jd}

Post Link: {post_link}
"""
    return body


def send_email(
    to_email, role, post_text, post_link,
    resume_path, recruiter_name=""
):
    """Send email to one recruiter. Returns True if sent."""

    to_email  = normalize_email(to_email)
    post_link = normalize_post_link(post_link)

    # ── Validation ─────────────────────────────────────────
    if not post_link:
        print(f"    ⚠  Skipped (no post link)  : {to_email}")
        return False

    if to_email in blocked_emails():
        print(f"    ⚠  Skipped (blocked email) : {to_email}")
        return False

    if already_sent(to_email, post_link):
        print(f"    ⚠  Skipped (already sent)  : {to_email}")
        return False

    # ── Subject ────────────────────────────────────────────
    subject = (
        f"{role['name']} | "
        f"{CANDIDATE['name']} | "
        f"{CANDIDATE['experience']} | "
        f"{CANDIDATE['work_auth']} | "
        f"Immediate"
    )

    body = build_email_body(role, post_text, post_link, recruiter_name)

    # ── Filter CC ──────────────────────────────────────────
    filtered_cc = [
        normalize_email(e)
        for e in CC_EMAILS
        if normalize_email(e) != to_email
    ]

    # ── Filter BCC ─────────────────────────────────────────
    filtered_bcc = [
        normalize_email(e)
        for e in BCC_EMAILS
        if normalize_email(e) != to_email
        and normalize_email(e) not in filtered_cc
    ]

    # ── Send ───────────────────────────────────────────────
    try:
        yag = yagmail.SMTP(GMAIL_ID, GMAIL_APP_PASSWORD)
        yag.send(
            to=to_email,
            cc=filtered_cc  if filtered_cc  else None,
            bcc=filtered_bcc if filtered_bcc else None,
            subject=subject,
            contents=body,
            attachments=str(resume_path),
        )
        yag.close()

        save_sent(to_email, post_link, role["name"])

        greeting_display = (
            f"Dear {recruiter_name},"
            if recruiter_name
            else "Dear Hiring Manager,"
        )

        print(f"    ✅ Sent     → {to_email}")
        print(f"    👤 Greeting → {greeting_display}")
        print(f"    📧 CC       → "
              f"{', '.join(filtered_cc) if filtered_cc else 'None'}")
        print(f"    📩 BCC      → "
              f"{', '.join(filtered_bcc) if filtered_bcc else 'None'}")
        print(f"    🔗 Post     → {post_link}")

        time.sleep(DELAY_BETWEEN_EMAILS)
        return True

    except Exception as e:
        print(f"    ❌ Failed   → {to_email} | Error: {e}")
        time.sleep(5)
        return False