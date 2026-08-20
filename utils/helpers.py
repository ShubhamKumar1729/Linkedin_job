import re

EMAIL_REGEX = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)


def clean(text):
    """Clean and normalize raw text."""
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_email(email):
    """Lowercase and strip punctuation from email."""
    email = clean(email).lower()
    email = email.strip(".,;:()[]{}<>\"'")
    return email


def normalize_post_link(raw_link):
    """Normalize and validate a LinkedIn post URL."""
    link = clean(str(raw_link or ""))
    if not link:
        return ""

    link = link.replace("&amp;", "&")
    link = link.replace("%3A", ":").replace("%3a", ":")
    link = link.replace("%2F", "/").replace("%2f", "/")

    m = re.search(r"urn:li:activity:\d+", link)
    if m:
        return f"https://www.linkedin.com/feed/update/{m.group(0)}/"

    m = re.search(r"activity[-:](\d{10,})", link)
    if m:
        return (
            f"https://www.linkedin.com/feed/update/"
            f"urn:li:activity:{m.group(1)}/"
        )

    if link.startswith("www.linkedin.com"):
        link = "https://" + link
    if link.startswith("/feed/update/") or link.startswith("/posts/"):
        link = "https://www.linkedin.com" + link

    link = link.split("?")[0].split("#")[0].rstrip("/ ") + "/"

    if (
        "linkedin.com/feed/update/" in link
        or "linkedin.com/posts/" in link
    ):
        return link

    return ""


def extract_emails(text):
    """Extract all unique valid-format emails from text."""
    text = clean(text)
    found = EMAIL_REGEX.findall(text)
    unique = []
    seen   = set()
    for email in found:
        email = normalize_email(email)
        if email and email not in seen:
            seen.add(email)
            unique.append(email)
    return unique