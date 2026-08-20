import time
from config.settings import PROFILE_DIR, SCROLL_ROUNDS


def launch_browser(playwright):
    """Launch persistent Chromium with saved LinkedIn session."""
    browser = playwright.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        viewport={"width": 1400, "height": 900},
        permissions=["clipboard-read", "clipboard-write"],
        args=["--start-maximized"],
    )
    return browser


def scroll_page(page, rounds=None):
    """Scroll down LinkedIn page to load more posts."""
    if rounds is None:
        rounds = SCROLL_ROUNDS
    for _ in range(rounds):
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(900)


def open_linkedin_and_check_login(page):
    """Open LinkedIn and check if already logged in."""
    print("\n  Opening LinkedIn...")
    page.goto("https://www.linkedin.com/feed/", timeout=60000)
    page.wait_for_timeout(5000)

    current_url = page.url

    if (
        "login"    in current_url or
        "signup"   in current_url or
        "authwall" in current_url
    ):
        print("\n" + "=" * 62)
        print("  ⚠  LinkedIn is NOT logged in!")
        print("=" * 62)
        print("\n  Please login manually in the browser.")
        input("  ▶ Press ENTER after fully logged in: ")
        page.wait_for_timeout(3000)
        print("  ✅ LinkedIn login successful!")
    else:
        print("  ✅ LinkedIn already logged in!")

    page.wait_for_timeout(2000)


def search_and_filter(page, role):
    """
    Automatically:
    1. Go to LinkedIn search URL directly
    2. Filter by Posts tab
    3. Apply Past 24 Hours filter
    """
    # Always use exactly what the user configured in .env. Relevance,
    # location, and recruiter quality are decided later by Groq.
    search_query = role["search"]
    print(f"\n  🔍 Auto searching exactly from .env: {search_query}")

    # ── Step 1: Use URL to search directly ────────────────
    # This is most reliable way - bypass search bar issues
    try:
        from urllib.parse import quote
        encoded_query = quote(search_query)

        # Go directly to LinkedIn search posts URL
        search_url = (
            f"https://www.linkedin.com/search/results/content/"
            f"?keywords={encoded_query}"
            f"&sortBy=date_posted"
        )

        page.goto(search_url, timeout=30000)
        page.wait_for_timeout(4000)
        print("  ✅ Search page loaded!")

    except Exception as e:
        print(f"  ⚠  URL navigation failed: {e}")
        # Fallback - try search bar
        _try_searchbar(page, search_query)

    # ── Step 2: Apply Past 24 Hours Filter ────────────────
    _apply_24h_filter(page)


def _try_searchbar(page, search_query):
    """Fallback: type in LinkedIn search bar."""
    try:
        # Click search bar
        page.click(
            "input[placeholder*='Search']",
            timeout=5000
        )
        page.wait_for_timeout(500)

        # Select all and delete
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        page.wait_for_timeout(300)

        # Type query
        page.keyboard.type(search_query, delay=50)
        page.wait_for_timeout(500)
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000)

        # Click Posts tab
        _click_posts_tab(page)

    except Exception as e:
        print(f"  ⚠  Search bar also failed: {e}")
        input("  ▶ Please search manually then press ENTER: ")


def _click_posts_tab(page):
    """Click the Posts filter tab on search results."""
    try:
        page.wait_for_timeout(2000)

        # Try direct text match
        selectors = [
            "button:has-text('Posts')",
            "a:has-text('Posts')",
            "li:has-text('Posts') button",
        ]

        for selector in selectors:
            try:
                el = page.locator(selector).first
                if el.count() > 0:
                    el.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    print("  ✅ Posts tab clicked!")
                    return
            except Exception:
                pass

        print("  ⚠  Could not click Posts tab")

    except Exception as e:
        print(f"  ⚠  Posts tab error: {e}")


def _apply_24h_filter(page):
    """Apply Past 24 Hours date filter."""
    try:
        page.wait_for_timeout(2000)

        # ── Try clicking Date Posted filter button ─────────
        date_filter_selectors = [
            "button:has-text('Date posted')",
            "button:has-text('All filters')",
            "button:has-text('Sort by')",
        ]

        clicked_filter = False
        for selector in date_filter_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0:
                    btn.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    clicked_filter = True
                    print(f"  ✅ Filter menu opened!")
                    break
            except Exception:
                pass

        if not clicked_filter:
            print("  ⚠  Filter button not found - trying URL param")
            # Add date filter via URL
            try:
                current_url = page.url
                if "datePosted" not in current_url:
                    if "?" in current_url:
                        new_url = current_url + "&datePosted=past-24h"
                    else:
                        new_url = current_url + "?datePosted=past-24h"
                    page.goto(new_url, timeout=30000)
                    page.wait_for_timeout(3000)
                    print("  ✅ 24h filter applied via URL!")
                    return
            except Exception:
                pass
            return

        # ── Click Past 24 Hours option ─────────────────────
        hour_selectors = [
            "label:has-text('Past 24 hours')",
            "span:has-text('Past 24 hours')",
            "div:has-text('Past 24 hours')",
            "li:has-text('Past 24 hours')",
        ]

        clicked_24h = False
        for selector in hour_selectors:
            try:
                opt = page.locator(selector).first
                if opt.count() > 0:
                    opt.click(timeout=3000)
                    page.wait_for_timeout(1000)
                    clicked_24h = True
                    print("  ✅ Past 24 hours selected!")
                    break
            except Exception:
                pass

        if not clicked_24h:
            try:
                page.get_by_text(
                    "Past 24 hours", exact=True
                ).click(timeout=3000)
                page.wait_for_timeout(1000)
                clicked_24h = True
                print("  ✅ Past 24 hours selected!")
            except Exception:
                pass

        if not clicked_24h:
            print("  ⚠  24h option not found")

        # ── Click Show Results / Apply button ──────────────
        show_selectors = [
            "button:has-text('Show results')",
            "button:has-text('Apply')",
            "button:has-text('Done')",
        ]

        for selector in show_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0:
                    btn.click(timeout=3000)
                    page.wait_for_timeout(3000)
                    print("  ✅ Results loaded with 24h filter!")
                    return
            except Exception:
                pass

        page.wait_for_timeout(3000)
        print("  ✅ Filter step done!")

    except Exception as e:
        print(f"  ⚠  Filter error: {e}")
        print("  Continuing without filter...")