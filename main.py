import time
import random
from playwright.sync_api import sync_playwright

from config.settings import (
    GMAIL_ID,
    GMAIL_APP_PASSWORD,
    RESUME_PATH,
    ROLES,
    MAX_EMAILS_PER_ROLE,
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
from core.scraper      import get_cards, get_post_link_from_card, extract_poster_name
from core.filters      import should_send_to_post, filter_recruiter_emails
from core.email_sender import send_email
from core.tracker      import load_sent_cache
from utils.helpers     import clean, extract_emails


def print_banner():
    print("\n" + "═" * 62)
    print("     LinkedIn Multi-Role Job Application Bot")
    print("═" * 62)
    print(f"  📄 Resume      : {RESUME_PATH.name}")
    print(f"  🎯 Total Roles : {len(ROLES)}")
    print(f"  📧 Max / Role  : {MAX_EMAILS_PER_ROLE} emails")
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

    for remaining in range(wait_seconds, 0, -5):
        print(f"  ⏱  {remaining:>4} seconds remaining...", end="\r")
        time.sleep(5)

    print(f"\n  ▶ Starting next role now!\n")


def process_role(page, role, resume_path):
    """
    Auto search + apply filters + scrape + send emails.
    Returns number of emails sent for this role.
    """
    role_sent = 0

    # ── Auto Search + Filter ───────────────────────────────
    search_and_filter(page, role)
    page.wait_for_timeout(3000)

    # ── Two passes ────────────────────────────────────────
    for pass_num in range(1, 3):

        if role_sent >= MAX_EMAILS_PER_ROLE:
            break

        cards = get_cards(page)
        print(f"\n  📋 Pass {pass_num} - Posts found: {len(cards)}")

        if not cards:
            print("  ⚠  No posts with emails visible.\n")

        for idx, card in enumerate(cards, start=1):

            if role_sent >= MAX_EMAILS_PER_ROLE:
                print(f"\n  🎯 Max {MAX_EMAILS_PER_ROLE} reached!")
                break

            try:
                post_text = clean(card.inner_text(timeout=2000))

                # Gate 1: filter post
                allowed, reason = should_send_to_post(post_text)
                if not allowed:
                    print(f"  {idx:>3}. ⛔ Skipped → {reason}")
                    continue

                # Gate 2: extract emails
                emails = filter_recruiter_emails(
                    extract_emails(post_text)
                )
                if not emails:
                    print(f"  {idx:>3}. ⛔ No valid email")
                    continue

                # Gate 3: get post link
                post_link = get_post_link_from_card(page, card)
                if not post_link:
                    print(f"  {idx:>3}. ⛔ No post link")
                    continue

                # Get recruiter name
                recruiter_name = extract_poster_name(card)

                print(f"\n  {idx:>3}. ✅ Valid post")
                print(f"       🔗 {post_link}")
                print(f"       👤 {recruiter_name or 'Name not found'}")
                print(f"       📧 {emails}")

                # Send email
                for email in emails:
                    if role_sent >= MAX_EMAILS_PER_ROLE:
                        break

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
                        print(
                            f"    📨 Progress: "
                            f"{role_sent}/{MAX_EMAILS_PER_ROLE}"
                        )

            except Exception as e:
                print(f"  {idx:>3}. ❌ Error: {e}")

        # Scroll after first pass
        if pass_num == 1:
            print(f"\n  📜 Scrolling for more posts...")
            scroll_page(page, rounds=SCROLL_ROUNDS)

    return role_sent


def main():

    # ── Checks ─────────────────────────────────────────────
    if not GMAIL_ID or not GMAIL_APP_PASSWORD:
        print("\n❌ Gmail credentials missing in .env!")
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
        page    = browser.new_page()

        # Check login once
        open_linkedin_and_check_login(page)

        # Loop roles
        for i, role in enumerate(ROLES):

            print_role_banner(role)

            role_sent    = process_role(page, role, RESUME_PATH)
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

            is_last = (i == len(ROLES) - 1)
            if not is_last:
                next_role = ROLES[i + 1]
                wait_between_roles(role["name"], next_role["name"])

        browser.close()

    # Final summary
    print("\n\n" + "═" * 62)
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
    main()