import json
import urllib.error
import urllib.request

from config.settings import GROQ_API_KEY, GROQ_MODEL


def groq_is_relevant(role, post_text):
    """
    Ask Groq if this post is a real hiring post worth applying to
    for the given role. Fail-open if Groq is missing or errors.
    Returns (allowed: bool, reason: str).
    """
    if not GROQ_API_KEY:
        return True, "Groq skipped (no GROQ_API_KEY)"

    snippet = (post_text or "")[:2500]
    prompt = f"""You decide if we should email a recruiter about this LinkedIn post.

Target role: {role.get('name', '')}
Candidate skills: {role.get('skills', '')}

Post:
\"\"\"{snippet}\"\"\"

Say YES if this is a real job / hiring / requirement / opening that is
even loosely related to the target role or nearby analyst / data / BI /
product / operations work. Location does NOT matter.

Say NO only if it is clearly:
- training, coaching, course, webinar, upskilling, placement guarantee
- bench sales / hotlist spam with no real opening
- not hiring at all

Reply with exactly two lines:
VERDICT: YES
or
VERDICT: NO
REASON: short reason
"""

    payload = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": "You filter LinkedIn job posts. Be slightly generous. Reply only VERDICT and REASON.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
        return True, f"Groq error, allowing post ({e})"

    upper = text.upper()
    reason = "Groq check"
    for line in text.splitlines():
        if line.lower().startswith("reason:"):
            reason = line.split(":", 1)[-1].strip() or reason

    if "VERDICT: NO" in upper or upper.startswith("NO"):
        return False, f"Groq: {reason}"

    return True, f"Groq: {reason}"
