import re
from utils.helpers import clean, extract_emails, normalize_post_link

JUNK_PHRASES = [
    "home my network jobs messaging",
    "skip to main content",
    "skip to search",
    "sort by",
    "content type",
]

# One in-page pass. Finds any block that contains an email — does not
# depend on LinkedIn class names (those change and were returning 0).
EXTRACT_JS = """
() => {
  const emailRe = /[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}/;
  const root = document.querySelector('main') || document.body;
  const hits = [];
  const nodes = root.querySelectorAll('li, article, section, div');
  for (const el of nodes) {
    const text = (el.innerText || '').trim();
    if (text.length < 50 || text.length > 7000) continue;
    if (!emailRe.test(text)) continue;
    hits.push(el);
    if (hits.length > 400) break;
  }
  const leaves = hits.filter(el => !hits.some(other => other !== el && el.contains(other)));

  const pickUrn = (el) => {
    const attrs = ['data-urn', 'data-chameleon-result-urn', 'data-id'];
    let node = el;
    for (let i = 0; i < 12 && node; i++) {
      for (const a of attrs) {
        const v = node.getAttribute && node.getAttribute(a);
        if (v && (String(v).includes('activity') || String(v).includes('ugcPost') || String(v).includes('urn:li'))) {
          return v;
        }
      }
      node = node.parentElement;
    }
    const html = (el.outerHTML || '').slice(0, 16000);
    const m = html.match(/urn:li:(?:activity|ugcPost):\\d+/);
    return m ? m[0] : '';
  };

  const seen = new Set();
  const out = [];
  for (const el of leaves) {
    const text = (el.innerText || '').trim();
    const key = text.slice(0, 280);
    if (seen.has(key)) continue;
    seen.add(key);
    const hrefs = Array.from(el.querySelectorAll('a[href]')).map(a => a.href || '');
    const href = hrefs.find(h => h.includes('/feed/update/') || h.includes('/posts/')) || '';
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
  return { scanned: hits.length, items: out };
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


def get_cards(page):
    """Return list of dicts: text, link, name."""
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
