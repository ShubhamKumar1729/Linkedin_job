import json
import urllib.error
import urllib.request

from config.settings import GROQ_API_KEY, GROQ_MODEL

_FALLBACK_MODELS = [
    GROQ_MODEL,
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama-3.3-8b-instruct",
    "gemma2-9b-it",
    "openai/gpt-oss-20b",
]

_working_model = None


def _call_groq(model, prompt):
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You filter LinkedIn job posts. Be slightly generous. "
                    "Reply only VERDICT and REASON."
                ),
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
            "User-Agent": "linkedin-job-bot/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip(),
            None,
        )
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")[:240]
        except Exception:
            pass
        return None, f"HTTP {e.code}: {body or e.reason}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return None, str(e)


def groq_is_relevant(role, post_text):
    """
    Ask Groq if this post is a real hiring post worth applying to.
    Fail-open if Groq is missing or errors.
    """
    global _working_model

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

    models = []
    if _working_model:
        models.append(_working_model)
    for m in _FALLBACK_MODELS:
        if m and m not in models:
            models.append(m)

    last_err = "unknown"
    for model in models:
        text, err = _call_groq(model, prompt)
        if text:
            _working_model = model
            upper = text.upper()
            reason = "relevant"
            for line in text.splitlines():
                if line.lower().startswith("reason:"):
                    reason = line.split(":", 1)[-1].strip() or reason
            if "VERDICT: NO" in upper or upper.strip().startswith("NO"):
                return False, f"Groq({model}): {reason}"
            return True, f"Groq({model}): {reason}"
        last_err = err or "empty response"

    return True, f"Groq error, allowing post ({last_err})"
