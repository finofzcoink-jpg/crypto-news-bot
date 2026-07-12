import os, requests, hashlib, re
import feedparser
from datetime import datetime

BASE44_APP_ID = os.environ["BASE44_APP_ID"]
BASE44_API_KEY = os.environ["BASE44_API_KEY"]

BASE44_URL = f"https://app.base44.com/api/apps/{BASE44_APP_ID}/entities/NewsArticle"

RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
]

# دسته‌بندی‌های مجاز طبق اسکیمای Base44
VALID_CATEGORIES = ["Bitcoin", "Altcoins", "DeFi", "NFT", "Regulation"]

def extract_image(entry):
    if "media_content" in entry and entry.media_content:
        return entry.media_content[0].get("url")
    if "media_thumbnail" in entry and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    match = re.search(r'<img[^>]+src="([^"]+)"', entry.get("summary", ""))
    if match:
        return match.group(1)
    return None

def has_good_image(url):
    if not url:
        return False
    try:
        r = requests.head(url, timeout=5)
        return r.status_code == 200 and "image" in r.headers.get("Content-Type", "")
    except Exception:
        return False

def clean_text(html_text):
    text = re.sub(r"<[^>]+>", " ", html_text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def guess_category(title, summary):
    text = (title + " " + summary).lower()
    if "bitcoin" in text or "btc" in text:
        return "Bitcoin"
    if "defi" in text:
        return "DeFi"
    if "nft" in text:
        return "NFT"
    if "regulat" in text or "sec " in text or "law" in text:
        return "Regulation"
    return "Altcoins"

def format_markdown(title, raw_html):
    body = clean_text(raw_html)
    return f"## {title}\n\n{body}"

def push_to_base44(entry, image_url):
    title = entry.get("title", "بدون عنوان")
    raw_summary = entry.get("summary", "")
    clean_summary = clean_text(raw_summary)
    published = entry.get("published", datetime.utcnow().isoformat())

    payload = {
        "title": title,
        "summary": clean_summary[:200] if clean_summary else title,
        "content": format_markdown(title, raw_summary),
        "category": guess_category(title, clean_summary),
        "image_url": image_url,
        "author": entry.get("source_name", "unknown"),
        "published_date": published,
    }

    r = requests.post(
        BASE44_URL,
        json=payload,
        headers={
            "api_key": BASE44_API_KEY,
            "Content-Type": "application/json"
        },
        timeout=10
    )
    print(title, "->", r.status_code, r.text[:200])

def main():
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        source_name = feed.feed.get("title", feed_url)
        for entry in feed.entries[:10]:
            entry["source_name"] = source_name
            image_url = extract_image(entry)
            if has_good_image(image_url):
                push_to_base44(entry, image_url)

if __name__ == "__main__":
    main()
