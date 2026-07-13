import os, requests, re, random
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup
from newspaper import Article  # نیاز به نصب newspaper4k در گیت‌هاب دارد

BASE44_APP_ID = os.environ["BASE44_APP_ID"]
BASE44_API_KEY = os.environ["BASE44_API_KEY"]

BASE44_URL = f"https://app.base44.com/api/apps/{BASE44_APP_ID}/entities/NewsArticle"

# لیست فیدهای رایگان با بالاترین نرخ پایداری و کمترین میزان مسدودسازی
RSS_FEEDS = [
    {"url": "https://cryptopotato.com/feed/", "source_name": "CryptoPotato"},
    {"url": "https://bitcoinist.com/feed/", "source_name": "Bitcoinist"},
    {"url": "https://beincrypto.com/feed/", "source_name": "BeInCrypto"},
    {"url": "https://decrypt.co/feed", "source_name": "Decrypt"},
]

MAX_CONTENT_LENGTH = 8000  

# هدرهای شبیه‌ساز مرورگرهای واقعی برای عبور ایمن از فایروال‌ها
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

def extract_high_quality_data(article_url, fallback_entry):
    """
    تلاش برای دریافت متن کامل و تصویر اصلی باکیفیت به کمک کتابخانه محبوب newspaper4k.
    در صورت بروز مشکل در دسترسی به صفحه، داده‌های پیش‌فرض RSS جایگزین می‌شوند.
    """
    full_text = ""
    image_url = None
    
    try:
        article = Article(article_url, language='en')
        # انتخاب تصادفی مرورگر برای هر درخواست جهت عبور از سیستم‌های ضدربات
        selected_ua = random.choice(USER_AGENTS)
        article.config.headers = {
            'User-Agent': selected_ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        article.download()
        article.parse()
        
        full_text = article.text.strip()
        image_url = article.top_image  # دریافت مستقیم عکس اصلی باکیفیت بالا
    except Exception as e:
        print(f"[INFO] Newspaper4k extraction skipped for {article_url}: {e}. Using RSS fallback...")

    # در صورتی که عکس باکیفیت دریافت نشد، جستجو در اطلاعات داخلی RSS انجام می‌شود
    if not image_url:
        image_url = extract_fallback_image(fallback_entry)

    # در صورتی که متن کامل دریافت نشد، خلاصه خبر RSS جایگزین می‌شود
    if not full_text:
        raw_html = fallback_entry.get("content", [{}])[0].get("value", "") if fallback_entry.get("content") else fallback_entry.get("summary", "")
        full_text = html_to_markdown(raw_html)

    return full_text, image_url

def extract_fallback_image(entry):
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
    """
    بررسی معتبر بودن لینک تصویر به شیوه‌ای بسیار پایدار
    """
    if not url:
        return False
    try:
        selected_ua = random.choice(USER_AGENTS)
        headers = {'User-Agent': selected_ua}
        r = requests.head(url, timeout=10, allow_redirects=True, headers=headers)
        
        # برخی سرورها درخواست‌های سریع HEAD را مسدود می‌کنند؛ در این حالت درخواست را با GET تکرار می‌کنیم
        if r.status_code not in [200, 301, 302]:
            r = requests.get(url, timeout=10, allow_redirects=True, headers=headers, stream=True)
            
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

def build_content(body_text, source_name):
    footer = f"\n\n---\n*Source: {source_name}*"
    max_body_len = MAX_CONTENT_LENGTH - len(footer) - 5
    body = body_text
    if len(body) > max_body_len:
        body = body[:max_body_len].rsplit(" ", 1)[0] + "…"
    return body + footer

def push_to_base44(entry, source_name):
    title = entry.get("title", "Untitled")
    link = entry.get("link")
    
    if not link:
        print(f"[SKIP] Link not found for: {title}")
        return

    # دریافت متن کامل خبر به همراه تصویر باکیفیت اصلی
    full_text, image_url = extract_high_quality_data(link, entry)
    
    # صحت‌سنجی نهایی وجود تصویر معتبر
    if not has_good_image(image_url):
        print(f"[SKIP] Image validation failed for: {title}")
        return

    published = get_published_date(entry)
    full_content = build_content(full_text, source_name)

    # ایجاد خودکار خلاصه کوتاه برای کارت‌های سایت‌ساز بیس 44 از روی متن تمیز شده اصلی
    plain_text = re.sub(r"[#*\-]", "", full_text)
    summary = re.sub(r"\s+", " ", plain_text).strip()[:220]

    payload = {
        "title": title[:200],
        "summary": summary if summary else title[:200],
        "content": full_content,
        "category": guess_category(title, plain_text),
        "image_url": image_url,
        "author": source_name,
        "published_date": published,
    }

    # ارسال نهایی به وب‌سایت در بیس 44
    r = requests.post(
        BASE44_URL,
        json=payload,
        headers={"api_key": BASE44_API_KEY, "Content-Type": "application/json"},
        timeout=25
    )
    print(title, "->", r.status_code, r.text[:300])

def main():
    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            if not feed.entries:
                print(f"[WARN] No entries found for {feed_info['source_name']}")
                continue
            
            # دریافت ۵ خبر آخر از هر فید برای کنترل حجم و ترافیک دیتابیس
            for entry in feed.entries[:5]:
                push_to_base44(entry, feed_info["source_name"])
        except Exception as e:
            print(f"[ERROR] {feed_info['source_name']}: {e}")

if __name__ == "__main__":
    main()
