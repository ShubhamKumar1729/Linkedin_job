import hashlib
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
    RECRUITER_POLICY,
    AI_RELEVANCE_THRESHOLD,
    MAX_EMAILS_PER_RUN,
    TARGET_EMAILS_PER_RUN,
    MAX_AGENCY_EMAIL_PERCENT,
    POSTS_PER_ROLE,
    MAX_PASSES_PER_ROLE,
    NO_NEW_POST_PASSES,
    MAX_EMAILS_PER_POST,
    MAX_EXPERIENCE_YEARS,
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
    print(
        f"  📧 Run Goal    : {TARGET_EMAILS_PER_RUN}-"
        f"{MAX_EMAILS_PER_RUN} quality emails"
    )
    print(f"  🧩 Agency Cap  : {MAX_AGENCY_EMAIL_PERCENT}% of successful sends")
    print(f"  🔎 Posts / Role: {POSTS_PER_ROLE} unique linked posts")
    print(
        f"  🔄 Search/Role : until post target or {NO_NEW_POST_PASSES} "
        f"no-new passes (safety max {MAX_PASSES_PER_ROLE})"
    )
    print(f"  🤖 Groq Model  : {GROQ_MODEL}")
    print(f"  🧭 Match Mode  : {AI_MATCH_MODE}")
    print(f"  🏢 Recruiters  : {RECRUITER_POLICY}")
    print(f"  🧑 Experience  : jobs requiring up to {MAX_EXPERIENCE_YEARS} years")
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


def process_role(page, role, resume_path, sent_before_role, agency_queue):
    """
    Search, filter, AI-check, and email jobs for one role.

    The run limit counts only successful sends. All job-level failures are
    isolated so the next visible post can still be processed.
    """
    role_sent = 0
    role_agency_queued = 0
    unique_emails_explored = set()
    ai_results_by_post = {}
    seen_card_keys = set()
    seen_post_links = set()
    link_failure_counts = {}
    no_new_post_passes = 0

    # ── Auto Search + Filter ───────────────────────────────
    search_and_filter(page, role)
    page.wait_for_timeout(3000)

    # Keep loading results until 30 unique linked posts are processed, the
    # Past-24-Hours result set is exhausted, or a safety/run limit is reached.
    for pass_num in range(1, MAX_PASSES_PER_ROLE + 1):

        if sent_before_role + role_sent >= MAX_EMAILS_PER_RUN:
            break

        print(f"\n  [SEARCH] Collecting post cards for pass {pass_num}...")
        scan_started = time.monotonic()
        cards = get_cards(page)
        print(
            f"  [SEARCH] Card scan completed in "
            f"{time.monotonic() - scan_started:.1f}s"
        )
        new_cards = []
        for card in cards:
            try:
                card_text = clean(card.inner_text(timeout=2000))
                card_key = hashlib.sha256(
                    card_text.encode("utf-8", errors="ignore")
                ).hexdigest()
                if not card_text or card_key in seen_card_keys:
                    continue
                seen_card_keys.add(card_key)
                new_cards.append((card, card_text, card_key))
            except Exception:
                pass

        print(
            f"\n  📋 Pass {pass_num} - Visible candidates: {len(cards)} | "
            f"Unseen cards: {len(new_cards)}"
        )

        if not cards:
            print("  [SKIP] No posts with recruiter emails visible.\n")
        elif not new_cards:
            print("  [SEARCH] No unseen candidate cards in this pass.\n")

        new_post_links_this_pass = 0
        for idx, (card, post_text, card_key) in enumerate(new_cards, start=1):

            if sent_before_role + role_sent >= MAX_EMAILS_PER_RUN:
                print(
                    f"\n  [STATS] Successful email limit reached: "
                    f"{MAX_EMAILS_PER_RUN}/{MAX_EMAILS_PER_RUN}"
                )
                break

            try:
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
                    failures = link_failure_counts.get(card_key, 0) + 1
                    link_failure_counts[card_key] = failures
                    if failures < 2:
                        # Give LinkedIn one later pass to finish rendering the
                        # card's permalink/URN without treating it as new data.
                        seen_card_keys.discard(card_key)
                    print("       [SKIP] Missing or invalid LinkedIn post link")
                    continue

                if post_link in seen_post_links:
                    print("       [SKIP] Post already processed in this role")
                    continue
                seen_post_links.add(post_link)
                new_post_links_this_pass += 1

                new_unique_emails = set(emails) - unique_emails_explored
                unique_emails_explored.update(emails)
                print(
                    f"       [EXPLORE] Posts: {len(seen_post_links)}/"
                    f"{POSTS_PER_ROLE} | Unique recruiter emails: "
                    f"{len(unique_emails_explored)}"
                    + (
                        f" (+{len(new_unique_emails)} new)"
                        if new_unique_emails
                        else ""
                    )
                )

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
                    ai_result = ai_results_by_post[ai_cache_key]
                    if ai_result is None:
                        print(
                            "       [AI] Previous AI attempt failed; "
                            "not retrying this post"
                        )
                    else:
                        print("       [AI] Reusing this run's previous decision")
                else:
                    print("       [AI] Sending complete job data to Groq...")
                    ai_result = evaluate_job_relevance(job_details, role)
                    # Cache failures too, otherwise every scroll pass hammers
                    # the same rate-limited post again.
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
                print(f"       [AI] Recruiter type: {ai_result['recruiter_type']}")
                print(
                    f"       [AI] Employer: "
                    f"{ai_result['employer'] or 'Not verified'}"
                )
                print(f"       [AI] Reason: {ai_result['reason']}")

                if not ai_approved:
                    print("       [SKIP] Job skipped")
                    continue

                if ai_result["recruiter_type"] == "staffing_agency":
                    for email in emails_to_send:
                        queue_key = (email, post_link)
                        if queue_key in agency_queue["keys"]:
                            continue
                        agency_queue["keys"].add(queue_key)
                        agency_queue["items"].append({
                            "to_email": email,
                            "role": role,
                            "post_text": post_text,
                            "post_link": post_link,
                            "resume_path": resume_path,
                            "recruiter_name": recruiter_name,
                            "employer": ai_result["employer"],
                            "score": score,
                            "reason": ai_result["reason"],
                        })
                        role_agency_queued += 1
                    print(
                        f"       [QUEUE] Vetted agency requisition queued; "
                        f"run-wide {MAX_AGENCY_EMAIL_PERCENT}% cap applies"
                    )
                    continue

                print(
                    "       [AI] Direct-employer email(s): "
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
                            f"       [STATS] Run: {run_sent}/"
                            f"{MAX_EMAILS_PER_RUN} emails sent"
                        )
                        print(
                            f"       [STATS] Role: {role_sent} quality sent | "
                            f"{len(seen_post_links)}/{POSTS_PER_ROLE} posts | "
                            f"{len(unique_emails_explored)} unique emails"
                        )
                    else:
                        print(
                            "       [EMAIL] Sending failed; continuing to "
                            "the next job"
                        )

            except Exception as e:
                print(f"  {idx:>3}. [ERROR] Job processing failed: {e}")
                print("       [SKIP] Job skipped safely")

        if new_post_links_this_pass:
            no_new_post_passes = 0
        else:
            no_new_post_passes += 1

        print(
            f"\n  [SEARCH] Post progress: {len(seen_post_links)}/"
            f"{POSTS_PER_ROLE}; new linked posts this pass: "
            f"{new_post_links_this_pass}"
        )

        if sent_before_role + role_sent >= MAX_EMAILS_PER_RUN:
            break

        # Finish the current loaded batch, then move on once at least the
        # configured number of unique linked posts has been processed.
        if len(seen_post_links) >= POSTS_PER_ROLE:
            print(
                f"\n  [SEARCH] Post target reached for {role['name']}: "
                f"{len(seen_post_links)}/{POSTS_PER_ROLE}."
            )
            break

        # Two consecutive passes without a new card are treated as exhaustion
        # of the currently available Past-24-Hours result set.
        if no_new_post_passes >= NO_NEW_POST_PASSES:
            print(
                f"\n  [SEARCH] No new Past-24-Hours posts after "
                f"{no_new_post_passes} passes; role results exhausted."
            )
            break

        if pass_num < MAX_PASSES_PER_ROLE:
            print(
                f"\n  📜 Scrolling for more posts "
                f"({len(seen_post_links)}/{POSTS_PER_ROLE} posts; "
                f"{len(unique_emails_explored)} unique emails; "
                f"{role_sent} quality sent)..."
            )
            scroll_page(page, rounds=SCROLL_ROUNDS)
            print("  [SEARCH] Scroll complete; scanning newly loaded posts...")

    if sent_before_role + role_sent < MAX_EMAILS_PER_RUN:
        if len(seen_post_links) >= POSTS_PER_ROLE:
            exploration_status = "30-post target achieved"
        elif no_new_post_passes >= NO_NEW_POST_PASSES:
            exploration_status = "Past-24-Hours results exhausted"
        else:
            exploration_status = "safety pass limit reached"
        pass_label = "pass" if pass_num == 1 else "passes"
        print(
            f"\n  [STATS] {role['name']}: processed "
            f"{len(seen_post_links)}/{POSTS_PER_ROLE} unique posts, found "
            f"{len(unique_emails_explored)} unique recruiter emails, sent "
            f"{role_sent} direct applications, queued {role_agency_queued} "
            f"vetted agency requisitions ({exploration_status}) after "
            f"{pass_num} {pass_label}"
        )

    return role_sent


def send_queued_agency_applications(agency_queue, direct_sent):
    """Send vetted agency requisitions without exceeding the run-wide cap."""
    if not agency_queue["items"] or MAX_AGENCY_EMAIL_PERCENT <= 0:
        return 0, {}

    direct_share = 100 - MAX_AGENCY_EMAIL_PERCENT
    allowed_by_ratio = (
        direct_sent * MAX_AGENCY_EMAIL_PERCENT // direct_share
        if direct_share > 0
        else len(agency_queue["items"])
    )
    allowed = min(
        allowed_by_ratio,
        MAX_EMAILS_PER_RUN - direct_sent,
        len(agency_queue["items"]),
    )

    print("\n" + "═" * 62)
    print("  🧩 VETTED AGENCY REQUISITION QUEUE")
    print("═" * 62)
    print(f"  Direct-employer emails sent : {direct_sent}")
    print(f"  Vetted agency candidates    : {len(agency_queue['items'])}")
    print(f"  Agency emails allowed       : {allowed}")
    print(f"  Agency percentage cap       : {MAX_AGENCY_EMAIL_PERCENT}%")

    agency_sent = 0
    agency_by_role = {}
    ranked_applications = sorted(
        agency_queue["items"],
        key=lambda item: item["score"],
        reverse=True,
    )
    for application in ranked_applications:
        if agency_sent >= allowed:
            break
        print(
            f"\n  [AGENCY] Sending vetted requisition for "
            f"{application['employer']} to {application['to_email']}"
        )
        success = send_email(
            to_email=application["to_email"],
            role=application["role"],
            post_text=application["post_text"],
            post_link=application["post_link"],
            resume_path=application["resume_path"],
            recruiter_name=application["recruiter_name"],
        )
        if success:
            agency_sent += 1
            role_name = application["role"]["name"]
            agency_by_role[role_name] = agency_by_role.get(role_name, 0) + 1
            print(
                f"  [STATS] Vetted agency: {agency_sent}/{allowed} | "
                f"Run total: {direct_sent + agency_sent}/{MAX_EMAILS_PER_RUN}"
            )

    return agency_sent, agency_by_role


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
    agency_queue = {"items": [], "keys": set()}

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        # Persistent Chromium normally starts with one tab. Reuse it and close
        # stale tabs restored from earlier automation runs.
        existing_pages = list(browser.pages)
        page = existing_pages[0] if existing_pages else browser.new_page()
        for extra_page in existing_pages[1:]:
            try:
                extra_page.close()
            except Exception:
                pass

        # Check login once before guarding against accidental popup tabs.
        open_linkedin_and_check_login(page)

        def close_unexpected_tab(new_page):
            if new_page == page:
                return
            print("  [BROWSER] Closing unexpected tab opened by page content")
            try:
                new_page.close()
            except Exception:
                pass

        browser.on("page", close_unexpected_tab)

        # Loop roles
        for i, role in enumerate(ROLES):

            print_role_banner(role)

            role_sent = process_role(
                page,
                role,
                RESUME_PATH,
                sent_before_role=grand_total,
                agency_queue=agency_queue,
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

    agency_sent, agency_by_role = send_queued_agency_applications(
        agency_queue,
        direct_sent=grand_total,
    )
    grand_total += agency_sent
    for entry in role_summary:
        entry["sent"] += agency_by_role.get(entry["role"], 0)

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
    print(f"  {'  Direct employer':<35} {grand_total - agency_sent:>6}")
    print(f"  {'  Vetted agency':<35} {agency_sent:>6}")
    print("═" * 62)
    if grand_total < TARGET_EMAILS_PER_RUN:
        print(
            f"  ⚠ Quality goal not reached: {grand_total}/"
            f"{TARGET_EMAILS_PER_RUN}. No lower-quality emails were forced."
        )
    print(f"\n  📁 Log: output/sent_emails.csv\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  [STOP] Automation stopped by user.\n")