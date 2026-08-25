import re
from utils.helpers import clean, extract_emails, normalize_post_link

JUNK_PHRASES = [
    "home my network jobs messaging",
    "skip to main content",
    "skip to search",
    "sort by",
    "content type",
]

# Expand each email hit up to the real post card so we keep data-urn / post hrefs.
EXTRACT_JS = """
() => {
  const emailRe = /[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}/;
  const root = document.querySelector('main') || document.body;

  const cardRoot = (el) => {
    let node = el;
    for (let i = 0; i < 22 && node && node !== document.body; i++) {
      const urn = node.getAttribute && (
        node.getAttribute('data-urn')
        || node.getAttribute('data-chameleon-result-urn')
        || node.getAttribute('data-id')
      );
      if (urn && /activity|ugcPost|urn:li/.test(String(urn))) return node;
      if (node.matches && node.matches(
        'div.feed-shared-update-v2, li.reusable-search__result-container, article, [data-view-name*="search-entity"]'
      )) return node;
      node = node.parentElement;
    }
    return el;
  };

  const pickUrn = (el) => {
    const attrs = ['data-urn', 'data-chameleon-result-urn', 'data-id'];
    let node = el;
    for (let i = 0; i < 14 && node; i++) {
      for (const a of attrs) {
        const v = node.getAttribute && node.getAttribute(a);
        if (v && /activity|ugcPost|urn:li/.test(String(v))) return v;
      }
      node = node.parentElement;
    }
    const html = (el.outerHTML || '').slice(0, 20000);
    const m = html.match(/urn:li:(?:activity|ugcPost):\\d+/);
    if (m) return m[0];
    const m2 = html.match(/activity[-:_](\\d{12,})/);
    return m2 ? ('urn:li:activity:' + m2[1]) : '';
  };

  const rawHits = [];
  const nodes = root.querySelectorAll('li, article, section, div');
  for (const el of nodes) {
    const text = (el.innerText || '').trim();
    if (text.length < 50 || text.length > 8000) continue;
    if (!emailRe.test(text)) continue;
    rawHits.push(el);
    if (rawHits.length > 500) break;
  }
  const leaves = rawHits.filter(el => !rawHits.some(o => o !== el && el.contains(o)));

  const seen = new Set();
  const out = [];
  for (const leaf of leaves) {
    const el = cardRoot(leaf);
    const text = (el.innerText || leaf.innerText || '').trim();
    const key = text.slice(0, 280);
    if (seen.has(key)) continue;
    seen.add(key);
    const hrefs = Array.from(el.querySelectorAll('a[href]')).map(a => a.href || '');
    const href = hrefs.find(h =>
      h.includes('/feed/update/') || h.includes('/posts/') || h.includes('activity')
    ) || '';
    const nameEl = el.querySelector(
      'span.update-components-actor__name, .update-components-actor__name, .feed-shared-actor__name, a.app-aware-link span[aria-hidden="true"]'
    );
    out.push({
      text,
      urn: pickUrn(el),
      href,
      name: nameEl ? (nameEl.innerText || '').trim().split(/\\s+/)[0] : '',
    });
  }
  return { scanned: rawHits.length, items: out };
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

    blob = f"{urn} {item.get('href') or ''} {item.get('text') or ''}"
    m = re.search(r"activity[-:_](\d{12,})", blob)
    if m:
        return f"https://www.linkedin.com/feed/update/urn:li:activity:{m.group(1)}/"
    return ""


def get_cards(page):
    try:
        raw = page.evaluate(EXTRACT_JS) or {}
    except Exception as e:
        print(f"     (card extract failed: {e})")
        raw = {}

    items = raw.get("items") if isinstance(raw, dict) else raw
    scanned = raw.get("scanned", len(items or [])) if isinstance(raw, dict) else 0
    items = items or []

    posts = []
    seen = set()
    for item in items:
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

    print(f"     (scanned {scanned} nodes, {len(posts)} with emails)")
    return posts
