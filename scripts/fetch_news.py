import os, requests, hashlib, re
from datetime import datetime

NEWS_API_KEY = os.environ["NEWS_API_KEY"]
BASE44_ENDPOINT = os.environ["BASE44_ENDPOINT"]
BASE44_SECRET = os.environ["BASE44_INGEST_SECRET"]

def fetch_raw_news():
    resp = requests.get(
        "https://cryptopanic.com/api/v1/posts/",
        params={"auth_token": NEWS_API_KEY, "filter": "hot", "public": "true"}
    )
    return resp.json().get("results", [])

def has_good_image(url):
    if not url:
        return False
    try:
        r = requests.head(url, timeout=5)
        return r.status_code == 200 and "image" in r.headers.get("Content-Type", "")
    except Exception:
        return False

def slugify(title):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return s[:80]

def format_markdown(title, raw_text):
    paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]
    body = "\n\n".join(paragraphs)
    return f"## {title}\n\n{body}"

def push_to_base44(item):
    payload = {
        "title": item["title"],
        "slug": slugify(item["title"]) + "-" + hashlib.md5(item["title"].encode()).hexdigest()[:6],
        "content": format_markdown(item["title"], item.get("body", item["title"])),
        "excerpt": item.get("body", "")[:200],
        "image_url": item["image"],
        "source_name": item.get("source", {}).get("title", "unknown"),
        "source_url": item["url"],
        "published_at": item.get("published_at", datetime.utcnow().isoformat()),
        "tags": [c["title"] for c in item.get("currencies", [])],
    }
    r = requests.post(
        BASE44_ENDPOINT,
        json=payload,
        headers={"x-api-key": BASE44_SECRET},
        timeout=10
    )
    print(payload["title"], "->", r.status_code)

def main():
    for item in fetch_raw_news():
        if has_good_image(item.get("image")):
            push_to_base44(item)

if __name__ == "__main__":
    main()
