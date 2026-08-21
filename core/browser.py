import time
from config.settings import (
    LINKEDIN_DATE_FILTER,
    LINKEDIN_DATE_FILTER_LABEL,
    PROFILE_DIR,
    SCROLL_ROUNDS,
)


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


def _scroll_metrics(page):
    """Return the active document/inner-container scroll position and height."""
    return page.evaluate("""
        () => {
            const root = document.scrollingElement || document.documentElement;
            const selectors = [
                '.scaffold-finite-scroll__content',
                '.search-results-container',
                'main'
            ];
            const containers = selectors
                .map(selector => document.querySelector(selector))
                .filter(Boolean)
                .filter(el => el.scrollHeight > el.clientHeight + 100);
            const inner = containers.sort(
                (a, b) => b.scrollHeight - a.scrollHeight
            )[0] || null;
            return {
                rootTop: root ? root.scrollTop : window.scrollY,
                rootHeight: root ? root.scrollHeight : document.body.scrollHeight,
                innerTop: inner ? inner.scrollTop : 0,
                innerHeight: inner ? inner.scrollHeight : 0,
            };
        }
    """)


def scroll_page(page, rounds=None):
    """Reliably scroll LinkedIn's document and any nested results container."""
    if rounds is None:
        rounds = SCROLL_ROUNDS

    moved_at_least_once = False
    for round_number in range(1, rounds + 1):
        try:
            before = _scroll_metrics(page)
            page.evaluate("""
                () => {
                    const amount = Math.max(window.innerHeight * 1.75, 1800);
                    const root = document.scrollingElement || document.documentElement;
                    if (root) {
                        root.scrollTop = Math.min(
                            root.scrollTop + amount,
                            root.scrollHeight
                        );
                    }
                    window.scrollBy(0, amount);

                    const selectors = [
                        '.scaffold-finite-scroll__content',
                        '.search-results-container',
                        'main'
                    ];
                    for (const selector of selectors) {
                        const el = document.querySelector(selector);
                        if (el && el.scrollHeight > el.clientHeight + 100) {
                            el.scrollTop = Math.min(
                                el.scrollTop + amount,
                                el.scrollHeight
                            );
                        }
                    }
                }
            """)
            page.wait_for_timeout(1200)
            after = _scroll_metrics(page)

            moved = (
                after["rootTop"] > before["rootTop"] + 5
                or after["rootHeight"] > before["rootHeight"] + 5
                or after["innerTop"] > before["innerTop"] + 5
                or after["innerHeight"] > before["innerHeight"] + 5
            )

            if not moved:
                # Fallback for LinkedIn layouts that only react to keyboard or
                # wheel input targeted at the viewport.
                page.keyboard.press("End")
                page.mouse.wheel(0, 2400)
                page.wait_for_timeout(1200)
                fallback_after = _scroll_metrics(page)
                moved = (
                    fallback_after["rootTop"] > after["rootTop"] + 5
                    or fallback_after["rootHeight"] > after["rootHeight"] + 5
                    or fallback_after["innerTop"] > after["innerTop"] + 5
                    or fallback_after["innerHeight"] > after["innerHeight"] + 5
                )
                after = fallback_after

            moved_at_least_once = moved_at_least_once or moved
            status = "moved" if moved else "at current bottom"
            print(
                f"  [SCROLL] {round_number}/{rounds}: {status} "
                f"(top {after['rootTop']:.0f}, height {after['rootHeight']:.0f})"
            )

        except Exception as exc:
            print(f"  [SCROLL] Round {round_number} failed: {exc}")

    return moved_at_least_once


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
    3. Apply the configured date-window filter
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
        if LINKEDIN_DATE_FILTER != "any-time":
            search_url += f"&datePosted={LINKEDIN_DATE_FILTER}"

        page.goto(search_url, timeout=30000)
        page.wait_for_timeout(4000)
        print("  ✅ Search page loaded!")

    except Exception as e:
        print(f"  ⚠  URL navigation failed: {e}")
        # Fallback - try search bar
        _try_searchbar(page, search_query)

    # ── Step 2: Apply configured date filter ──────────────
    _apply_date_filter(page)

    # Ensure no filter popover intercepts wheel/keyboard scrolling, then start
    # result exploration from the top of the page.
    try:
        page.keyboard.press("Escape")
        page.evaluate("""
            () => {
                const root = document.scrollingElement || document.documentElement;
                if (root) root.scrollTop = 0;
                window.scrollTo(0, 0);
                for (const selector of [
                    '.scaffold-finite-scroll__content',
                    '.search-results-container',
                    'main'
                ]) {
                    const el = document.querySelector(selector);
                    if (el && el.scrollHeight > el.clientHeight + 100) {
                        el.scrollTop = 0;
                    }
                }
            }
        """)
    except Exception:
        pass


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


def _apply_date_filter(page):
    """Apply the configured LinkedIn content-search date filter."""
    if LINKEDIN_DATE_FILTER == "any-time":
        print("  ✅ Date filter: Any time")
        return

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
                        new_url = (
                            current_url
                            + f"&datePosted={LINKEDIN_DATE_FILTER}"
                        )
                    else:
                        new_url = (
                            current_url
                            + f"?datePosted={LINKEDIN_DATE_FILTER}"
                        )
                    page.goto(new_url, timeout=30000)
                    page.wait_for_timeout(3000)
                    print(
                        f"  ✅ {LINKEDIN_DATE_FILTER_LABEL} filter applied via URL!"
                    )
                    return
                print(
                    f"  ✅ {LINKEDIN_DATE_FILTER_LABEL} already applied via URL!"
                )
            except Exception:
                pass
            return

        # ── Click configured date option ───────────────────
        date_option_selectors = [
            f"label:has-text('{LINKEDIN_DATE_FILTER_LABEL}')",
            f"span:has-text('{LINKEDIN_DATE_FILTER_LABEL}')",
            f"div:has-text('{LINKEDIN_DATE_FILTER_LABEL}')",
            f"li:has-text('{LINKEDIN_DATE_FILTER_LABEL}')",
        ]

        clicked_date = False
        for selector in date_option_selectors:
            try:
                opt = page.locator(selector).first
                if opt.count() > 0:
                    opt.click(timeout=3000)
                    page.wait_for_timeout(1000)
                    clicked_date = True
                    print(f"  ✅ {LINKEDIN_DATE_FILTER_LABEL} selected!")
                    break
            except Exception:
                pass

        if not clicked_date:
            try:
                page.get_by_text(
                    LINKEDIN_DATE_FILTER_LABEL, exact=True
                ).click(timeout=3000)
                page.wait_for_timeout(1000)
                clicked_date = True
                print(f"  ✅ {LINKEDIN_DATE_FILTER_LABEL} selected!")
            except Exception:
                pass

        if not clicked_date:
            print(f"  ⚠  {LINKEDIN_DATE_FILTER_LABEL} option not found")

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
                    print(
                        f"  ✅ Results loaded with {LINKEDIN_DATE_FILTER_LABEL} filter!"
                    )
                    return
            except Exception:
                pass

        page.wait_for_timeout(3000)
        print("  ✅ Filter step done!")

    except Exception as e:
        print(f"  ⚠  Filter error: {e}")
        print("  Continuing without filter...")