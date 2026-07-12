import os, requests, hashlib, re
import feedparser
from datetime import datetime

BASE44_ENDPOINT = os.environ["BASE44_ENDPOINT"]
BASE44_SECRET = os.environ["BASE44_INGEST_SECRET"]

# فیدهای رایگان خبری کریپتو - بدون نیاز به API Key
RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
]

def extract_image(entry):
    # خیلی از فیدها عکس رو توی media_content یا media_thumbnail می‌ذارن
    if "media_content" in entry and entry.media_content:
        return entry.media_content[0].get("url")
    if "media_thumbnail" in entry and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    # بعضی وقت‌ها عکس داخل خود summary/description به‌صورت تگ <img> هست
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
    # حذف تگ‌های HTML از متن خام
    text = re.sub(r"<[^>]+>", " ", html_text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def slugify(title):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return s[:80]

def format_markdown(title, raw_html):
    body = clean_text(raw_html)
    return f"## {title}\n\n{body}"

def push_to_base44(entry, image_url):
    title = entry.get("title", "بدون عنوان")
    raw_summary = entry.get("summary", "")
    published = entry.get("published", datetime.utcnow().isoformat())

    payload = {
        "title": title,
        "slug": slugify(title) + "-" + hashlib.md5(title.encode()).hexdigest()[:6],
        "content": format_markdown(title, raw_summary),
        "excerpt": clean_text(raw_summary)[:200],
        "image_url": image_url,
        "source_name": entry.get("source_name", "unknown"),
        "source_url": entry.get("link", ""),
        "published_at": published,
        "tags": [],
    }
    r = requests.post(
        BASE44_ENDPOINT,
        json=payload,
        headers={"x-api-key": BASE44_SECRET},
        timeout=10
    )
    print(title, "->", r.status_code)

def main():
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        source_name = feed.feed.get("title", feed_url)
        for entry in feed.entries[:10]:  # فقط ۱۰ خبر آخر هر منبع
            entry["source_name"] = source_name
            image_url = extract_image(entry)
            if has_good_image(image_url):
                push_to_base44(entry, image_url)

if __name__ == "__main__":
    main()
