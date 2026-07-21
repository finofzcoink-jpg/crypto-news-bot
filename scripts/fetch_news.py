import os
import re
import random
import requests
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup
from newspaper import Article
from urllib.parse import urljoin

BASE44_APP_ID = os.environ.get("BASE44_APP_ID", "")
BASE44_API_KEY = os.environ.get("BASE44_API_KEY", "")
BASE44_URL = f"https://app.base44.com/api/apps/{BASE44_APP_ID}/entities/NewsArticle"

RSS_FEEDS = [
    {"url": "https://cointelegraph.com/rss", "source_name": "Cointelegraph"},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source_name": "CoinDesk"},
    {"url": "https://decrypt.co/feed", "source_name": "Decrypt"},
    {"url": "https://cryptoslate.com/feed/", "source_name": "CryptoSlate"},
    {"url": "https://beincrypto.com/feed/", "source_name": "BeInCrypto"},
]

MAX_CONTENT_LENGTH = 7000

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
]

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

def normalize_image_url(img_url, base_url):
    """تبدیل آدرس‌های نسبی عکس به آدرس کامل و استاندارد"""
    if not img_url or not isinstance(img_url, str):
        return None
    img_url = img_url.strip()
    if img_url.startswith("//"):
        return "https:" + img_url
    if img_url.startswith("/"):
        return urljoin(base_url, img_url)
    return img_url

def is_valid_image(url):
    """بررسی زنده سالم بودن و معتبر بودن آدرس تصویر"""
    if not url or not isinstance(url, str):
        return False
    
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
        
    # فیلتر آیکون‌ها، لوگوها و تصاویر بسیار کوچک
    bad_keywords = ['logo', 'icon', 'avatar', '150x150', '300x300', 'placeholder', '.svg']
    if any(bad in url.lower() for bad in bad_keywords):
        return False

    try:
        # ارسال درخواست تست برای اطمینان از سلامت لینک عکس
        r = requests.head(url, headers=get_headers(), timeout=6, allow_redirects=True)
        if r.status_code != 200:
            r = requests.get(url, headers=get_headers(), timeout=6, allow_redirects=True, stream=True)
        
        c_type = r.headers.get("Content-Type", "").lower()
        has_img_ext = any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.avif'])
        return r.status_code == 200 and ("image" in c_type or has_img_ext)
    except Exception:
        return False

def fetch_html_bs4(url):
    try:
        resp = requests.get(url, headers=get_headers(), timeout=12)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, 'html.parser')
    except Exception:
        pass
    return None

def extract_hd_meta_image(soup, article_url):
    if not soup:
        return None
    
    meta_tags = [
        {'property': 'og:image'},
        {'name': 'og:image'},
        {'name': 'twitter:image'},
        {'property': 'twitter:image'}
    ]
    
    for tag_attr in meta_tags:
        tag = soup.find('meta', tag_attr)
        if tag and tag.get('content'):
            img_url = tag['content'].strip()
            normalized = normalize_image_url(img_url, article_url)
            if normalized:
                return normalized
    return None

def extract_rss_image(entry, article_url):
    url = None
    if "media_content" in entry and entry.media_content:
        url = entry.media_content[0].get("url")
    elif "media_thumbnail" in entry and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get("url")
    elif entry.get("enclosures"):
        for enc in entry.enclosures:
            if "image" in enc.get("type", ""):
                url = enc.get("href") or enc.get("url")
                break
    return normalize_image_url(url, article_url)

def extract_article_details(article_url, fallback_entry):
    full_text = ""
    image_url = None
    soup = fetch_html_bs4(article_url)

    # ۱. استخراج عکس از متاتگ‌های اصلی وب‌سایت
    if soup:
        image_url = extract_hd_meta_image(soup, article_url)

    # ۲. استفاده از Newspaper4k
    try:
        article = Article(article_url, language='en')
        article.config.headers = get_headers()
        article.download()
        article.parse()

        full_text = article.text.strip()
        if not image_url and article.top_image:
            image_url = normalize_image_url(article.top_image, article_url)
    except Exception as e:
        print(f"[INFO] Scraping via Newspaper4k failed for {article_url}: {e}")

    # ۳. استخراج عکس از فید RSS
    if not image_url:
        image_url = extract_rss_image(fallback_entry, article_url)

    if not full_text:
        raw_html = fallback_entry.get("content", [{}])[0].get("value", "") if fallback_entry.get("content") else fallback_entry.get("summary", "")
        full_text = clean_html_to_text(raw_html)

    return full_text, image_url

def clean_html_to_text(html_text):
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator="\n\n")
    return re.sub(r'\n{3,}', '\n\n', text).strip()

def guess_category(title, text):
    content = (title + " " + text).lower()
    if any(k in content for k in ["bitcoin", "btc", "satoshi"]):
        return "Bitcoin"
    if any(k in content for k in ["defi", "uniswap", "aave", "yield"]):
        return "DeFi"
    if any(k in content for k in ["nft", "opensea", "blur", "collectible"]):
        return "NFT"
    if any(k in content for k in ["sec", "law", "court", "regulate", "binance", "ftx"]):
        return "Regulation"
    return "Altcoins"

def format_rich_content(body_text, source_name):
    paragraphs = [p.strip() for p in body_text.split('\n') if len(p.strip()) > 30]
    
    formatted_body = ""
    if paragraphs:
        formatted_body += f"{paragraphs[0]}\n\n"
        formatted_body += "\n\n".join(paragraphs[1:])
    else:
        formatted_body = body_text

    footer = f"\n\n---\nSource: {source_name}"
    max_len = MAX_CONTENT_LENGTH - len(footer)
    if len(formatted_body) > max_len:
        formatted_body = formatted_body[:max_len].rsplit(" ", 1)[0] + "…"
        
    return formatted_body + footer

def push_to_base44(entry, source_name):
    title = entry.get("title", "").strip()
    link = entry.get("link")

    if not link or not title:
        return

    full_text, image_url = extract_article_details(link, entry)

    # فیلتر ۱: اگر متن خبر خیلی کوتاه باشد
    if len(full_text.split()) < 100:
        print(f"[SKIP] Article too short: {title}")
        return

    # فیلتر ۲ (اصلی): اگر عکس وجود نداشته باشد یا لینک عکس خراب/غیرمعتبر باشد، خبر اصلاً فرستاده نمی‌شود
    if not is_valid_image(image_url):
        print(f"[SKIP - NO IMAGE] No valid working image found for: {title}")
        return

    category = guess_category(title, full_text)
    full_content = format_rich_content(full_text, source_name)

    clean_summary = re.sub(r'[\#\*\_]', '', full_text)
    summary = " ".join(clean_summary.split()[:35]) + "..."

    published_parsed = entry.get("published_parsed")
    published_date = datetime(*published_parsed[:6]).strftime("%Y-%m-%d") if published_parsed else datetime.utcnow().strftime("%Y-%m-%d")

    payload = {
        "title": title[:200],
        "summary": summary,
        "content": full_content,
        "category": category,
        "image_url": image_url,
        "author": source_name,
        "published_date": published_date,
        "status": "published",
        "published": True,
        "is_published": True
    }

    try:
        res = requests.post(
            BASE44_URL,
            json=payload,
            headers={"api_key": BASE44_API_KEY, "Content-Type": "application/json"},
            timeout=20
        )
        print(f"[SUCCESS] {title[:40]}... | Image: Validated OK | Status: {res.status_code}")
    except Exception as e:
        print(f"[ERROR] Base44 push failed: {e}")

def main():
    if not BASE44_APP_ID or not BASE44_API_KEY:
        print("[ERROR] Base44 environment variables are missing!")
        return

    for feed_info in RSS_FEEDS:
        print(f"\n--- Fetching from: {feed_info['source_name']} ---")
        try:
            feed = feedparser.parse(feed_info["url"])
            if not feed.entries:
                print(f"[WARN] No entries found for {feed_info['source_name']}")
                continue

            for entry in feed.entries[:3]:
                push_to_base44(entry, feed_info["source_name"])
        except Exception as e:
            print(f"[ERROR] Fetching feed {feed_info['source_name']}: {e}")

if __name__ == "__main__":
    main()
