import os, requests, re
import feedparser
from datetime import datetime

BASE44_APP_ID = os.environ["BASE44_APP_ID"]
BASE44_API_KEY = os.environ["BASE44_API_KEY"]

BASE44_URL = f"https://app.base44.com/api/apps/{BASE44_APP_ID}/entities/NewsArticle"

RSS_FEEDS = [
    {"url": "https://cryptoslate.com/feed/", "source_name": "CryptoSlate"},
    {"url": "https://www.prnewswire.com/rss/financial-services-latest-news/cryptocurrency-list.rss", "source_name": "PR Newswire"},
]

MAX_CONTENT_LENGTH = 3000  # جلوگیری از رد شدن از سقف احتمالی فیلد content

def extract_image(entry):
    if "media_content" in entry and entry.media_content:
        return entry.media_content[0].get("url")
    if "media_thumbnail" in entry and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    if entry.get("enclosures"):
        for enc in entry.enclosures:
            if "image" in enc.get("type", ""):
                return enc.get("href") or enc.get("url")
    raw = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else entry.get("summary", "")
    match = re.search(r'<img[^>]+src="([^"]+)"', raw)
    if match:
        return match.group(1)
    return None

def has_good_image(url):
    if not url:
        return False
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return r.status_code == 200 and "image" in r.headers.get("Content-Type", "")
    except Exception:
        return False

def html_to_markdown(html_text):
    text = html_text or ""
    text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n## \1\n", text, flags=re.DOTALL)
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def get_full_content(entry):
    if entry.get("content"):
        return entry["content"][0]["value"]
    return entry.get("summary", "")

def get_published_date(entry):
    published_parsed = entry.get("published_parsed")
    if published_parsed:
        return datetime(*published_parsed[:6]).strftime("%Y-%m-%d")
    return datetime.utcnow().strftime("%Y-%m-%d")

def guess_category(title, text):
    t = (title + " " + text).lower()
    if "bitcoin" in t or "btc" in t:
        return "Bitcoin"
    if "defi" in t:
        return "DeFi"
    if "nft" in t:
        return "NFT"
    if "regulat" in t or "sec " in t or "law" in t:
        return "Regulation"
    return "Altcoins"

def build_content(markdown_body, source_name):
    footer = f"\n\n---\n*Source: {source_name}*"
    max_body_len = MAX_CONTENT_LENGTH - len(footer) - 5
    body = markdown_body
    if len(body) > max_body_len:
        body = body[:max_body_len].rsplit(" ", 1)[0] + "…"
    return body + footer

def push_to_base44(entry, image_url, source_name):
    title = entry.get("title", "Untitled")
    raw_html = get_full_content(entry)
    markdown_body = html_to_markdown(raw_html)
    published = get_published_date(entry)

    full_content = build_content(markdown_body, source_name)

    plain_text = re.sub(r"[#*\-]", "", markdown_body)
    summary = re.sub(r"\s+", " ", plain_text).strip()[:200]

    payload = {
        "title": title[:200],
        "summary": summary if summary else title[:200],
        "content": full_content,
        "category": guess_category(title, plain_text),
        "image_url": image_url,
        "author": source_name,
        "published_date": published,
    }

    r = requests.post(
        BASE44_URL,
        json=payload,
        headers={"api_key": BASE44_API_KEY, "Content-Type": "application/json"},
        timeout=20
    )
    print(title, "->", r.status_code, r.text[:300])

def main():
    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            if not feed.entries:
                print(f"[WARN] No entries for {feed_info['source_name']}")
                continue
            for entry in feed.entries[:10]:
                image_url = extract_image(entry)
                if has_good_image(image_url):
                    push_to_base44(entry, image_url, feed_info["source_name"])
                else:
                    print(f"[SKIP] No good image: {entry.get('title', '')}")
        except Exception as e:
            print(f"[ERROR] {feed_info['source_name']}: {e}")

if __name__ == "__main__":
    main()
