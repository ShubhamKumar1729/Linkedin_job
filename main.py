import time
import random
from playwright.sync_api import sync_playwright

from config.settings import (
    GMAIL_ID,
    GMAIL_APP_PASSWORD,
    RESUME_PATH,
    ROLES,
    MAX_EMAILS_PER_ROLE,
    MIN_EMAILS_PER_ROLE,
    SCROLL_ROUNDS,
    SCRAPE_PASSES,
    WAIT_BETWEEN_ROLES_MIN,
    WAIT_BETWEEN_ROLES_MAX,
    GROQ_API_KEY,
)
from core.browser      import (
    launch_browser,
    scroll_page,
    open_linkedin_and_check_login,
    search_and_filter,
)
from core.scraper      import get_cards, get_post_link_from_card, extract_poster_name
from core.filters      import should_send_to_post, filter_recruiter_emails
from core.groq_filter  import groq_is_relevant
from core.email_sender import send_email
from core.tracker      import load_sent_cache, already_sent
from utils.helpers     import clean, extract_emails


def print_banner():
    print("\n" + "═" * 62)
    print("     LinkedIn Multi-Role Job Application Bot")
    print("═" * 62)
    print(f"  📄 Resume      : {RESUME_PATH.name}")
    print(f"  🎯 Total Roles : {len(ROLES)}")
    print(f"  📧 Max / Role  : {MAX_EMAILS_PER_ROLE} emails")
    print(f"  🎯 Min / Role  : {MIN_EMAILS_PER_ROLE} emails")
    print(f"  🤖 Groq        : {'ON' if GROQ_API_KEY else 'OFF (set GROQ_API_KEY)'}")
    print(f"  🔁 Passes      : {SCRAPE_PASSES}")
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
        step = 5 if remaining >= 5 else remaining
        time.sleep(step)
        remaining -= step

    print("\n  ▶ Starting next role now!\n")


def process_role(page, role, resume_path):
    role_sent = 0
    seen_posts = set()
    total_passes = max(2, SCRAPE_PASSES)

    search_and_filter(page, role)
    page.wait_for_timeout(4000)

    for pass_num in range(1, total_passes + 1):
        if role_sent >= MAX_EMAILS_PER_ROLE:
            break

        cards = get_cards(page)
        print(f"\n  📋 Pass {pass_num}/{total_passes} - Posts found: {len(cards)}")

        if not cards:
            print("  ⚠  No posts with emails visible.\n")

        for idx, card in enumerate(cards, start=1):
            if role_sent >= MAX_EMAILS_PER_ROLE:
                print(f"\n  🎯 Max {MAX_EMAILS_PER_ROLE} reached!")
                break

            try:
                post_text = clean(card.get("text") if isinstance(card, dict) else "")
                if not post_text:
                    continue

                allowed, reason = should_send_to_post(post_text)
                if not allowed:
                    print(f"  {idx:>3}. ⛔ Skipped → {reason}")
                    continue

                groq_ok, groq_reason = groq_is_relevant(role, post_text)
                print(f"  {idx:>3}. 🤖 {groq_reason}")
                if not groq_ok:
                    print("       ⛔ Groq said not relevant")
                    continue

                emails = filter_recruiter_emails(extract_emails(post_text))
<<<<<<< HEAD
                if not emails:
                    print("       ⛔ No valid email")
                    continue

                post_link = get_post_link_from_card(page, card)
=======
                emails = [e for e in emails if not already_sent(e)]
                if not emails:
                    print("       ⛔ No new email (already contacted or invalid)")
                    continue

                post_link = card.get("link") if isinstance(card, dict) else ""
>>>>>>> 8732080 (Stop Playwright freezes and skip duplicate recruiter inboxes.)
                if not post_link:
                    print("       ⚠  No LinkedIn URL — sending with text fallback id")
                    post_link = f"fallback:{emails[0]}"

                if post_link in seen_posts:
                    print("       ⛔ Duplicate post")
                    continue
                seen_posts.add(post_link)

<<<<<<< HEAD
                recruiter_name = extract_poster_name(card)
=======
                recruiter_name = ""
                if isinstance(card, dict):
                    recruiter_name = card.get("name") or ""
>>>>>>> 8732080 (Stop Playwright freezes and skip duplicate recruiter inboxes.)

                print("       ✅ Valid post")
                print(f"       🔗 {post_link}")
                print(f"       👤 {recruiter_name or 'Name not found'}")
                print(f"       📧 {emails}")

                for email in emails:
                    if role_sent >= MAX_EMAILS_PER_ROLE:
                        break
                    if already_sent(email):
                        print(f"    ⚠  Skipped (already sent)  : {email}")
                        continue

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

        if role_sent >= MAX_EMAILS_PER_ROLE:
            break

        if pass_num < total_passes:
            print("\n  📜 Scrolling for more posts...")
            scroll_page(page, rounds=SCROLL_ROUNDS)

    if role_sent < MIN_EMAILS_PER_ROLE:
        print(
            f"\n  ⚠  Only {role_sent}/{MIN_EMAILS_PER_ROLE} "
            f"minimum emails found for this role."
        )

    return role_sent


def main():
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

    grand_total = 0
    role_summary = []

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        page = browser.new_page()

        open_linkedin_and_check_login(page)

        for i, role in enumerate(ROLES):
            print_role_banner(role)

            role_sent = process_role(page, role, RESUME_PATH)
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

            if i != len(ROLES) - 1:
                wait_between_roles(role["name"], ROLES[i + 1]["name"])

        browser.close()

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
    print("\n  📁 Log: output/sent_emails.csv\n")


if __name__ == "__main__":
    main()
