import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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

    m = re.search(r"urn:li:(?:activity|ugcPost):\d+", link)
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


def normalize_application_url(raw_url):
    """Normalize a LinkedIn Jobs or external company/ATS application URL."""
    url = clean(str(raw_url or "")).replace("&amp;", "&").strip("<>\"'()[] ")
    if not url.startswith(("https://", "http://")):
        return ""

    try:
        parts = urlsplit(url)
    except ValueError:
        return ""

    host = parts.netloc.lower().split(":", 1)[0]
    path = parts.path.lower()
    if not host:
        return ""

    ats_hosts = (
        "myworkdayjobs.com", "greenhouse.io", "lever.co", "ashbyhq.com",
        "smartrecruiters.com", "icims.com", "jobvite.com",
        "successfactors.com", "oraclecloud.com",
    )
    looks_actionable = (
        (host.endswith("linkedin.com") and "/jobs/view/" in path)
        or any(host.endswith(ats_host) for ats_host in ats_hosts)
        or any(token in path for token in ("/careers", "/career", "/jobs", "/job/", "/apply"))
    )
    if not looks_actionable:
        return ""

    # Remove only marketing parameters; preserve requisition/job identifiers.
    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"trk", "trackingid", "ref", "source"}
    ])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


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