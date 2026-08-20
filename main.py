import time
import random
from playwright.sync_api import sync_playwright

from config.settings import (
    GMAIL_ID,
    GMAIL_APP_PASSWORD,
    RESUME_PATH,
    ROLES,
    GROQ_API_KEY,
    GROQ_MODEL,
    AI_MATCH_MODE,
    AI_RELEVANCE_THRESHOLD,
    MAX_EMAILS_PER_RUN,
    MAX_EMAILS_PER_POST,
    MAX_JOB_DESCRIPTION_CHARS,
    SCROLL_ROUNDS,
    WAIT_BETWEEN_ROLES_MIN,
    WAIT_BETWEEN_ROLES_MAX,
)
from core.browser      import (
    launch_browser,
    scroll_page,
    open_linkedin_and_check_login,
    search_and_filter,
)
from core.scraper      import (
    get_cards,
    get_post_link_from_card,
    extract_poster_name,
    extract_job_details,
)
from core.filters      import filter_recruiter_emails
from core.groq_service import evaluate_job_relevance
from core.email_sender import send_email
from core.tracker      import already_sent, load_sent_cache
from utils.helpers     import clean, extract_emails


def print_banner():
    print("\n" + "═" * 62)
    print("     LinkedIn Multi-Role Job Application Bot")
    print("═" * 62)
    print(f"  📄 Resume      : {RESUME_PATH.name}")
    print(f"  🎯 Total Roles : {len(ROLES)}")
    print(f"  📧 Max / Run   : {MAX_EMAILS_PER_RUN} successful emails")
    print(f"  🤖 Groq Model  : {GROQ_MODEL}")
    print(f"  🧭 Match Mode  : {AI_MATCH_MODE}")
    print(f"  ✅ AI Threshold: {AI_RELEVANCE_THRESHOLD}")
    print(f"  ⏳ Wait/Role   : "
          f"{WAIT_BETWEEN_ROLES_MIN}-{WAIT_BETWEEN_ROLES_MAX} seconds")
    print("═" * 62)
    print("\n  Roles queued:")
    for role in ROLES:
        print(f"    {role['index']:>2}. {role['name']}")
    print()


def print_role_banner(role):
    print("\n" + "═" * 62)
    print(f"  🎯 ROLE {role['index']}: {role['name']}")
    print(f"  🔧 Skills  : {role['skills']}")
    print(f"  🔍 Search  : {role['search']}")
    print("═" * 62)


def wait_between_roles(current_role_name, next_role_name):
    """Countdown wait between roles."""
    wait_seconds = random.randint(
        WAIT_BETWEEN_ROLES_MIN,
        WAIT_BETWEEN_ROLES_MAX,
    )
    print(f"\n  {'─' * 58}")
    print(f"  ✅ Finished : {current_role_name}")
    print(f"  ⏭  Up next  : {next_role_name}")
    print(f"  ⏳ Waiting  : {wait_seconds} seconds")
    print(f"  {'─' * 58}")

    remaining = wait_seconds
    while remaining > 0:
        print(f"  ⏱  {remaining:>4} seconds remaining...", end="\r")
        sleep_seconds = min(5, remaining)
        time.sleep(sleep_seconds)
        remaining -= sleep_seconds

    print("\n  ▶ Starting next role now!\n")


def process_role(page, role, resume_path, sent_before_role):
    """
    Search, filter, AI-check, and email jobs for one role.

    The run limit counts only successful sends. All job-level failures are
    isolated so the next visible post can still be processed.
    """
    role_sent = 0
    ai_results_by_post = {}

    # ── Auto Search + Filter ───────────────────────────────
    search_and_filter(page, role)
    page.wait_for_timeout(3000)

    # ── Two passes ────────────────────────────────────────
    for pass_num in range(1, 3):

        if sent_before_role + role_sent >= MAX_EMAILS_PER_RUN:
            break

        cards = get_cards(page)
        print(f"\n  📋 Pass {pass_num} - Posts found: {len(cards)}")

        if not cards:
            print("  [SKIP] No posts with recruiter emails visible.\n")

        for idx, card in enumerate(cards, start=1):

            if sent_before_role + role_sent >= MAX_EMAILS_PER_RUN:
                print(
                    f"\n  [STATS] Successful email limit reached: "
                    f"{MAX_EMAILS_PER_RUN}/{MAX_EMAILS_PER_RUN}"
                )
                break

            try:
                post_text = clean(card.inner_text(timeout=2000))
                if not post_text:
                    print(f"  {idx:>3}. [SKIP] Missing job description")
                    continue

                job_details = extract_job_details(post_text, role)
                job_title = job_details["job_title"]
                company = job_details["company"]
                print(f"\n  {idx:>3}. [JOB] Found: {job_title} - {company}")

                # Find recruiter email before evaluating the job.
                emails = filter_recruiter_emails(extract_emails(post_text))
                if not emails:
                    print("       [SKIP] Missing or invalid recruiter email")
                    continue
                print(f"       [EMAIL] Recruiter email found: {', '.join(emails)}")

                # A real LinkedIn job post normally has only a small number of
                # contacts and a bounded post body. Larger values indicate that
                # LinkedIn returned a parent page container combining many posts.
                if len(emails) > MAX_EMAILS_PER_POST:
                    print(
                        "       [SKIP] Combined LinkedIn container detected "
                        f"({len(emails)} emails)"
                    )
                    continue
                if len(post_text) > MAX_JOB_DESCRIPTION_CHARS:
                    print(
                        "       [SKIP] Oversized combined LinkedIn container "
                        f"({len(post_text)} characters)"
                    )
                    continue

                # Do not make role/location/bench/training decisions here.
                # Groq receives the complete post and is the only relevance
                # gate after deterministic email/data validation.
                print("       [DATA] Basic data valid; Groq will decide")

                post_link = get_post_link_from_card(page, card)
                if not post_link:
                    print("       [SKIP] Missing or invalid LinkedIn post link")
                    continue

                # Avoid an unnecessary AI request when every email/post pair
                # has already been recorded by the existing CSV tracker.
                unsent_emails = []
                for email in emails:
                    if already_sent(email, post_link):
                        print(
                            f"       [SKIP] Duplicate application already sent: "
                            f"{email}"
                        )
                    else:
                        unsent_emails.append(email)

                if not unsent_emails:
                    continue

                job_details["recruiter_emails"] = unsent_emails
                ai_cache_key = (post_link, tuple(sorted(unsent_emails)))

                recruiter_name = extract_poster_name(card)
                print(f"       🔗 {post_link}")
                print(f"       👤 {recruiter_name or 'Name not found'}")

                # Groq only decides relevance and which supplied recruiter
                # emails genuinely belong to this opening. It never sends.
                if ai_cache_key in ai_results_by_post:
                    print("       [AI] Reusing this run's previous decision")
                    ai_result = ai_results_by_post[ai_cache_key]
                else:
                    print("       [AI] Sending complete job data to Groq...")
                    ai_result = evaluate_job_relevance(job_details, role)
                    if ai_result is not None:
                        ai_results_by_post[ai_cache_key] = ai_result

                if ai_result is None:
                    print("       [SKIP] Job skipped safely after AI failure")
                    continue

                score = ai_result["score"]
                approved_email_set = set(ai_result["approved_emails"])
                emails_to_send = [
                    email for email in unsent_emails
                    if email in approved_email_set
                ]
                ai_approved = (
                    ai_result["relevant"]
                    and score >= AI_RELEVANCE_THRESHOLD
                    and bool(emails_to_send)
                )
                decision = "RELEVANT" if ai_approved else "NOT RELEVANT"

                print(f"       [AI] Relevance score: {score}")
                print(f"       [AI] Decision: {decision}")
                print(f"       [AI] Reason: {ai_result['reason']}")

                if not ai_approved:
                    print("       [SKIP] Job skipped")
                    continue

                print(
                    "       [AI] Genuine recruiter email(s): "
                    + ", ".join(emails_to_send)
                )

                for email in emails_to_send:
                    if sent_before_role + role_sent >= MAX_EMAILS_PER_RUN:
                        break

                    print(f"       [EMAIL] Sending application to {email}...")
                    success = send_email(
                        to_email=email,
                        role=role,
                        post_text=post_text,
                        post_link=post_link,
                        resume_path=resume_path,
                        recruiter_name=recruiter_name,
                    )

                    if success:
                        role_sent += 1
                        run_sent = sent_before_role + role_sent
                        print("       [EMAIL] Application sent successfully")
                        print(
                            f"       [STATS] {run_sent}/"
                            f"{MAX_EMAILS_PER_RUN} emails sent"
                        )
                    else:
                        print(
                            "       [EMAIL] Sending failed; continuing to "
                            "the next job"
                        )

            except Exception as e:
                print(f"  {idx:>3}. [ERROR] Job processing failed: {e}")
                print("       [SKIP] Job skipped safely")

        # Scroll after first pass unless the successful-send limit was met.
        if (
            pass_num == 1
            and sent_before_role + role_sent < MAX_EMAILS_PER_RUN
        ):
            print("\n  📜 Scrolling for more posts...")
            scroll_page(page, rounds=SCROLL_ROUNDS)

    return role_sent


def main():

    # ── Checks ─────────────────────────────────────────────
    if not GMAIL_ID or not GMAIL_APP_PASSWORD:
        print("\n❌ Gmail credentials missing in .env!")
        return

    if not GROQ_API_KEY:
        print("\n❌ GROQ_API_KEY is missing in .env!")
        return

    if not GROQ_MODEL:
        print("\n❌ GROQ_MODEL is missing in .env!")
        return

    if not ROLES:
        print("\n❌ No roles found in .env!")
        return

    if not RESUME_PATH.exists():
        print(f"\n❌ Resume not found: {RESUME_PATH}")
        return

    print_banner()
    load_sent_cache()

    grand_total  = 0
    role_summary = []

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        # Persistent Chromium normally starts with one tab. Reuse it instead
        # of opening an unnecessary second tab on every run.
        page = browser.pages[0] if browser.pages else browser.new_page()

        # Check login once
        open_linkedin_and_check_login(page)

        # Loop roles
        for i, role in enumerate(ROLES):

            print_role_banner(role)

            role_sent = process_role(
                page,
                role,
                RESUME_PATH,
                sent_before_role=grand_total,
            )
            grand_total += role_sent

            role_summary.append({
                "role": role["name"],
                "sent": role_sent,
            })

            print(f"\n  ┌{'─' * 50}┐")
            print(f"  │  ✅ Role   : {role['name']:<38}│")
            print(f"  │  📨 Sent   : {role_sent:<38}│")
            print(f"  │  📊 Total  : {grand_total:<38}│")
            print(f"  └{'─' * 50}┘")

            limit_reached = grand_total >= MAX_EMAILS_PER_RUN
            if limit_reached:
                print(
                    f"\n  [STATS] Run stopped after {grand_total} successful "
                    "application emails."
                )
                break

            is_last = (i == len(ROLES) - 1)
            if not is_last:
                next_role = ROLES[i + 1]
                wait_between_roles(role["name"], next_role["name"])

        browser.close()

    # Final summary
    print("\n\n" + "═" * 62)
    if grand_total >= MAX_EMAILS_PER_RUN:
        print("  ✅ SUCCESSFUL EMAIL LIMIT REACHED!")
    else:
        print("  ✅ ALL ROLES COMPLETED!")
    print("═" * 62)
    print(f"  {'Role':<35} {'Sent':>6}")
    print(f"  {'─'*35} {'─'*6}")
    for entry in role_summary:
        print(f"  {entry['role']:<35} {entry['sent']:>6}")
    print(f"  {'─'*35} {'─'*6}")
    print(f"  {'TOTAL':<35} {grand_total:>6}")
    print("═" * 62)
    print(f"\n  📁 Log: output/sent_emails.csv\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  [STOP] Automation stopped by user.\n")