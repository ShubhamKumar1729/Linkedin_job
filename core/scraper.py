import re
from urllib.parse import urljoin
from utils.helpers import clean, extract_emails, normalize_post_link

JUNK_PHRASES = [
    "home my network jobs messaging",
    "skip to main content",
    "skip to search",
    "sort by",
    "content type",
]

CARD_SELECTORS = [
    "div.feed-shared-update-v2",
    "li.reusable-search__result-container",
    "div[data-urn]",
    "article",
    "main div",
]


def extract_poster_name(card):
    """
    Try to extract the name of the person who made the post.
    Returns first name only or empty string if not found.
    """
    # Try common LinkedIn name selectors
    name_selectors = [
        "span.update-components-actor__name",
        "span.app-aware-link span[aria-hidden='true']",
        ".feed-shared-actor__name",
        ".update-components-actor__name",
        "a.app-aware-link span",
        ".actor-name",
    ]

    for selector in name_selectors:
        try:
            el = card.locator(selector).first
            if el.count() > 0:
                name = clean(el.inner_text(timeout=1000))
                if name and len(name) > 1 and len(name) < 60:
                    # Return only first name
                    first_name = name.strip().split()[0]
                    # Clean any junk
                    first_name = re.sub(r"[^a-zA-Z\-]", "", first_name)
                    if first_name:
                        return first_name
        except Exception:
            pass

    return ""


def get_post_link_from_card(page, card):
    """
    Try two methods to extract LinkedIn post URL from a card.
    Method 1: scan anchor hrefs inside the card
    Method 2: click more options button and copy link
    """

    # Method 1 - href scan
    try:
        hrefs = card.evaluate("""
            el => Array.from(el.querySelectorAll('a[href]'))
                .map(a => a.href || a.getAttribute('href'))
                .filter(Boolean)
        """)
        for href in hrefs:
            href  = urljoin("https://www.linkedin.com", href)
            fixed = normalize_post_link(href)
            if fixed:
                return fixed
    except Exception:
        pass

    # Method 2 - clipboard copy via more options button
    try:
        buttons = card.locator("button").all()
        for btn in buttons:
            label = (btn.get_attribute("aria-label") or "").lower()
            if any(w in label for w in ["more", "control", "actions"]):
                btn.click(timeout=2000)
                page.wait_for_timeout(800)

                for option_text in [
                    "Copy link to post",
                    "Copy link to this post",
                    "Copy link",
                ]:
                    try:
                        opt = page.get_by_text(
                            option_text, exact=False
                        ).first
                        if opt.count() > 0:
                            opt.click(timeout=2000)
                            page.wait_for_timeout(800)
                            copied = page.evaluate(
                                "navigator.clipboard.readText()"
                            )
                            page.keyboard.press("Escape")
                            fixed = normalize_post_link(copied)
                            if fixed:
                                return fixed
                    except Exception:
                        pass

        page.keyboard.press("Escape")
    except Exception:
        pass

    return ""


def get_cards(page):
    """
    Scrape all visible LinkedIn post cards that contain emails.
    Returns deduplicated list of card elements.
    """

    # Expand truncated post text
    try:
        more_buttons = page.get_by_text("more", exact=False)
        for i in range(min(more_buttons.count(), 20)):
            try:
                more_buttons.nth(i).click(timeout=800)
                page.wait_for_timeout(250)
            except Exception:
                pass
    except Exception:
        pass

    cards = []

    for selector in CARD_SELECTORS:
        try:
            found = page.locator(selector).all()
            for card in found:
                try:
                    text = clean(card.inner_text(timeout=1000))

                    # Skip short or empty cards
                    if len(text) < 40:
                        continue

                    # Must have at least one email
                    if not extract_emails(text):
                        continue

                    # Skip navigation / UI junk
                    low = text.lower()
                    if any(j in low for j in JUNK_PHRASES):
                        continue

                    cards.append(card)

                except Exception:
                    pass
        except Exception:
            pass

    # Deduplicate by first 700 chars of text
    unique = []
    seen   = set()
    for card in cards:
        try:
            key = clean(card.inner_text(timeout=800))[:700]
            if key not in seen:
                seen.add(key)
                unique.append(card)
        except Exception:
            pass

    return unique