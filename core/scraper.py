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
    "div.feed-shared-update-v2__control-menu-container",
    "li.reusable-search__result-container",
    "div[data-urn*='activity']",
    "div[data-urn*='ugcPost']",
    "article",
]


def _safe_text(card, timeout=1000):
    try:
        return clean(card.inner_text(timeout=timeout))
    except Exception:
        return ""


def extract_poster_name(card):
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
                if name and 1 < len(name) < 60:
                    first_name = name.strip().split()[0]
                    first_name = re.sub(r"[^a-zA-Z\-]", "", first_name)
                    if first_name:
                        return first_name
        except Exception:
            pass

    return ""


def _link_from_urn(card):
    try:
        urn = card.evaluate(
            """el => {
                const node = el.closest('[data-urn]')
                    || (el.hasAttribute && el.hasAttribute('data-urn') ? el : null)
                    || el.querySelector('[data-urn]');
                return node ? (node.getAttribute('data-urn') || '') : '';
            }"""
        )
    except Exception:
        urn = ""

    urn = clean(urn)
    if not urn:
        return ""

    if urn.startswith("urn:li:activity:") or urn.startswith("urn:li:ugcPost:"):
        return f"https://www.linkedin.com/feed/update/{urn}/"

    m = re.search(r"(urn:li:(?:activity|ugcPost):\d+)", urn)
    if m:
        return f"https://www.linkedin.com/feed/update/{m.group(1)}/"
    return ""


def get_post_link_from_card(page, card):
    # Method 0 - data-urn on the card (most reliable)
    urn_link = _link_from_urn(card)
    if urn_link:
        return urn_link

    # Method 1 - href scan
    try:
        hrefs = card.evaluate(
            """
            el => Array.from(el.querySelectorAll('a[href]'))
                .map(a => a.href || a.getAttribute('href'))
                .filter(Boolean)
            """
        )
        for href in hrefs:
            href = urljoin("https://www.linkedin.com", href)
            fixed = normalize_post_link(href)
            if fixed:
                return fixed
    except Exception:
        pass

    # Method 2 - copy link from more menu
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
                        opt = page.get_by_text(option_text, exact=False).first
                        if opt.count() > 0:
                            opt.click(timeout=2000)
                            page.wait_for_timeout(800)
                            copied = page.evaluate("navigator.clipboard.readText()")
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
    try:
        more_buttons = page.get_by_text("…more", exact=False)
        for i in range(min(more_buttons.count(), 25)):
            try:
                more_buttons.nth(i).click(timeout=800)
                page.wait_for_timeout(200)
            except Exception:
                pass
    except Exception:
        pass

    try:
        more_buttons = page.get_by_text("see more", exact=False)
        for i in range(min(more_buttons.count(), 15)):
            try:
                more_buttons.nth(i).click(timeout=800)
                page.wait_for_timeout(200)
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
                    text = _safe_text(card, timeout=1200)
                    if len(text) < 40:
                        continue
                    if not extract_emails(text):
                        continue
                    low = text.lower()
                    if any(j in low for j in JUNK_PHRASES):
                        continue
                    cards.append(card)
                except Exception:
                    pass
        except Exception:
            pass

    unique = []
    seen = set()
    for card in cards:
        key = _safe_text(card, timeout=800)[:700]
        if key and key not in seen:
            seen.add(key)
            unique.append(card)

    return unique
