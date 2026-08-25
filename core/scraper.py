import re
from utils.helpers import clean, extract_emails, normalize_post_link

JUNK_PHRASES = [
    "home my network jobs messaging",
    "skip to main content",
    "skip to search",
    "sort by",
    "content type",
]

# Keep this list tight. Scanning every `main div` freezes Playwright.
CARD_SELECTORS = [
    "div.feed-shared-update-v2",
    "li.reusable-search__result-container",
    "div.reusable-search__result-container",
    "div[data-chameleon-result-urn]",
    "div[data-urn*='activity']",
    "div[data-urn*='ugcPost']",
]

EXTRACT_JS = """
(sels) => {
  const seen = new Set();
  const out = [];
  const pickUrn = (el) => {
    const attrs = ['data-urn', 'data-chameleon-result-urn', 'data-id'];
    let node = el;
    for (let i = 0; i < 10 && node; i++) {
      for (const a of attrs) {
        const v = node.getAttribute && node.getAttribute(a);
        if (v && (v.includes('activity') || v.includes('ugcPost') || v.includes('urn:li'))) {
          return v;
        }
      }
      node = node.parentElement;
    }
    const html = (el.outerHTML || '').slice(0, 12000);
    const m = html.match(/urn:li:(?:activity|ugcPost):\\d+/);
    return m ? m[0] : '';
  };
  const pickName = (el) => {
    const n = el.querySelector(
      'span.update-components-actor__name, .update-components-actor__name, .feed-shared-actor__name'
    );
    return n ? (n.innerText || '').trim().split(/\\s+/)[0] : '';
  };
  const pickHref = (el) => {
    const as = Array.from(el.querySelectorAll('a[href]')).map(a => a.href || '');
    return as.find(h => h.includes('/feed/update/') || h.includes('/posts/')) || '';
  };
  for (const sel of sels) {
    document.querySelectorAll(sel).forEach((el) => {
      const text = (el.innerText || '').trim();
      if (text.length < 40) return;
      const key = text.slice(0, 400);
      if (seen.has(key)) return;
      seen.add(key);
      out.push({
        text,
        urn: pickUrn(el),
        href: pickHref(el),
        name: pickName(el),
      });
    });
  }
  return out;
}
"""


def _link_from_item(item):
    urn = clean(item.get("urn") or "")
    m = re.search(r"(urn:li:(?:activity|ugcPost):\d+)", urn)
    if m:
        return f"https://www.linkedin.com/feed/update/{m.group(1)}/"

    href = normalize_post_link(item.get("href") or "")
    if href:
        return href

    htmlish = f"{urn} {item.get('href') or ''} {item.get('text') or ''}"
    m = re.search(r"activity[-:_](\d{12,})", htmlish)
    if m:
        return f"https://www.linkedin.com/feed/update/urn:li:activity:{m.group(1)}/"
    return ""


def extract_poster_name(card_or_item):
    if isinstance(card_or_item, dict):
        name = clean(card_or_item.get("name") or "")
        name = re.sub(r"[^a-zA-Z\-]", "", name.split()[0] if name else "")
        return name
    return ""


def get_post_link_from_card(_page, card_or_item):
    if isinstance(card_or_item, dict):
        return _link_from_item(card_or_item)
    return ""


def get_cards(page):
    """Return list of dicts: text, link, name. One JS pass — no per-node hangs."""
    try:
        raw = page.evaluate(EXTRACT_JS, CARD_SELECTORS) or []
    except Exception as e:
        print(f"     (card extract failed: {e})")
        raw = []

    posts = []
    seen = set()
    for item in raw:
        text = clean(item.get("text") or "")
        if len(text) < 40:
            continue
        if not extract_emails(text):
            continue
        low = text.lower()
        if any(j in low for j in JUNK_PHRASES):
            continue
        link = _link_from_item(item)
        key = (link or "") + "|" + text[:250]
        if key in seen:
            continue
        seen.add(key)
        name = clean(item.get("name") or "")
        if name:
            name = re.sub(r"[^a-zA-Z\-]", "", name.split()[0])
        posts.append({"text": text, "link": link, "name": name})

    print(f"     (scanned {len(raw)} cards, {len(posts)} with emails)")
    return posts
