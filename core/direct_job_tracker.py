import csv
import time

from config.settings import DIRECT_JOBS_FILE
from utils.helpers import normalize_application_url, normalize_post_link

_DIRECT_JOB_CACHE = set()


def _cache_key(application_url, post_link):
    application_url = normalize_application_url(application_url)
    post_link = normalize_post_link(post_link)
    if application_url:
        return ("application_url", application_url)
    return ("post_link", post_link)


def load_direct_job_cache():
    """Load previously saved direct-employer application links."""
    global _DIRECT_JOB_CACHE
    _DIRECT_JOB_CACHE = set()

    if not DIRECT_JOBS_FILE.exists():
        return

    try:
        with DIRECT_JOBS_FILE.open("r", newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                application_url = normalize_application_url(
                    row.get("application_url", "")
                )
                post_link = normalize_post_link(row.get("post_link", ""))
                if application_url or post_link:
                    _DIRECT_JOB_CACHE.add(
                        _cache_key(application_url, post_link)
                    )
        print(
            f"  Loaded {len(_DIRECT_JOB_CACHE)} saved direct-employer job links."
        )
    except Exception as exc:
        print(f"  Could not load direct-job cache: {exc}")


def direct_job_already_saved(application_url, post_link):
    return _cache_key(application_url, post_link) in _DIRECT_JOB_CACHE


def save_direct_job(role, job_details, application_url, post_link, reason):
    """Append one unique direct-employer job/application URL to CSV."""
    application_url = normalize_application_url(application_url)
    post_link = normalize_post_link(post_link)
    if not application_url:
        return False

    key = _cache_key(application_url, post_link)
    if key in _DIRECT_JOB_CACHE:
        return False

    DIRECT_JOBS_FILE.parent.mkdir(exist_ok=True)
    fieldnames = [
        "time",
        "role",
        "job_title",
        "company",
        "location",
        "application_url",
        "post_link",
        "ai_reason",
    ]
    write_header = not DIRECT_JOBS_FILE.exists()

    with DIRECT_JOBS_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "role": role.get("name", ""),
            "job_title": job_details.get("job_title", ""),
            "company": job_details.get("company", ""),
            "location": job_details.get("location", ""),
            "application_url": application_url,
            "post_link": post_link,
            "ai_reason": reason,
        })

    _DIRECT_JOB_CACHE.add(key)
    return True
