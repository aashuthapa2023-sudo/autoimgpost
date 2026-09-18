# -*- coding: utf-8 -*-
"""
web_scraper.py - Free internet news sourcing for Netflix and Hollywood content.
Pulls from public RSS feeds: Deadline, Variety, ScreenRant, TheWrap, Decider.
Extracts og:image from each article page with HTML entity decoding.
Returns posts in the exact same dict format as ingestion.py.
"""
import re
import time
import html as html_module
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# Direct publisher RSS feeds work better than Google News because their
# article pages have proper og:image tags and don't redirect to google.com
NETFLIX_RSS_FEEDS = [
    "https://deadline.com/category/streaming/feed/",
    "https://screenrant.com/tag/netflix/feed/",
    "https://www.thewrap.com/category/streaming/feed/",
    "https://variety.com/t/netflix/feed/",
    "https://decider.com/feed/",
]

HOLLYWOOD_RSS_FEEDS = [
    "https://deadline.com/category/film/feed/",
    "https://variety.com/v/film/feed/",
    "https://screenrant.com/tag/movies/feed/",
    "https://www.thewrap.com/category/movies/feed/",
    "https://collider.com/feed/",
]

MIXED_RSS_FEEDS = [
    "https://deadline.com/feed/",
    "https://variety.com/feed/",
    "https://screenrant.com/feed/",
    "https://www.thewrap.com/feed/",
]

CATEGORY_MAP = {
    "netflix": NETFLIX_RSS_FEEDS,
    "hollywood": HOLLYWOOD_RSS_FEEDS,
    "mixed": MIXED_RSS_FEEDS,
}

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _caption_fingerprint(text):
    return hashlib.md5(re.sub(r"\s+", "", text[:80]).lower().encode("utf-8")).hexdigest()


def _story_fingerprint(text):
    words = re.findall(r"[a-z]{4,}", text.lower())
    top = sorted(set(words), key=lambda w: -words.count(w))[:8]
    return "_".join(sorted(top))


def _parse_pub_date(date_str):
    if not date_str:
        return 0
    try:
        dt = parsedate_to_datetime(date_str.strip())
        return int(dt.timestamp())
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(date_str.strip().replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return 0


def _clean_img_url(raw_url):
    """Decode HTML entities and strip trailing junk from image URLs."""
    if not raw_url:
        return ""
    cleaned = html_module.unescape(raw_url.strip())
    # Remove trailing HTML entity artifacts like &#038; that appear in some feeds
    cleaned = re.sub(r"&#\d+;.*$", "", cleaned)
    return cleaned.strip()


def _fetch_og_image(article_url, timeout=12):
    """Fetch og:image or twitter:image from an article page."""
    if not article_url or not article_url.startswith("http"):
        return ""
    try:
        resp = requests.get(article_url, headers=SCRAPE_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        page = resp.text

        # All common og:image / twitter:image meta tag orderings
        patterns = [
            r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'name=["\']twitter:image:src["\'][^>]+content=["\']([^"\']+)["\']',
            r'name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]
        for pat in patterns:
            m = re.search(pat, page, re.IGNORECASE)
            if m:
                img = _clean_img_url(m.group(1))
                if img.startswith("http"):
                    return img

        # Fallback: largest image found in srcset attributes
        srcsets = re.findall(r'srcset=["\']([^"\']+)["\']', page)
        for srcset in srcsets:
            parts = [p.strip().split()[0] for p in srcset.split(",") if p.strip()]
            for p in reversed(parts):
                p = _clean_img_url(p)
                if p.startswith("http") and any(e in p.lower() for e in [".jpg", ".jpeg", ".png", ".webp"]):
                    return p

    except Exception:
        pass
    return ""


def _validate_image_url(img_url, timeout=8):
    """Confirm image URL is reachable and not a tiny icon/thumbnail."""
    if not img_url:
        return False
    try:
        r = requests.head(img_url, headers=SCRAPE_HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code in (200, 206):
            ct = r.headers.get("Content-Type", "")
            if ct and not any(x in ct for x in ["image/", "jpeg", "png", "webp", "gif"]):
                return False
            cl = int(r.headers.get("Content-Length", "0") or "0")
            # Reject only if Content-Length is explicitly tiny (< 10 KB)
            if cl > 0 and cl < 10000:
                return False
            return True
        # Some CDNs reject HEAD — fall back to streaming GET
        r2 = requests.get(img_url, headers=SCRAPE_HEADERS, timeout=timeout, allow_redirects=True, stream=True)
        if r2.status_code not in (200, 206):
            return False
        ct = r2.headers.get("Content-Type", "")
        if ct and not any(x in ct for x in ["image/", "jpeg", "png", "webp"]):
            return False
        return True
    except Exception:
        return False


def _parse_rss_feed(feed_url, max_items=15):
    """Parse one RSS feed, return list of article dicts."""
    items = []
    try:
        resp = requests.get(feed_url, headers=SCRAPE_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        # Strip unknown namespace prefixes that cause "unbound prefix" errors in ET
        raw = resp.content
        raw_text = raw.decode("utf-8", errors="replace")
        # Remove xmlns declarations and prefixed tags that ET can't handle
        raw_text = re.sub(r'\s+xmlns:[a-z0-9]+="[^"]+"', "", raw_text)
        raw_text = re.sub(r'<[a-z0-9]+:[a-z0-9]+[^>]*/>', "", raw_text)  # self-closing prefixed tags
        raw_text = re.sub(r'<(/)?[a-z]{2,10}:(?!feed|entry|link|title|updated|id)[a-z]+[^>]*>', "", raw_text)
        raw = raw_text.encode("utf-8")
        root = ET.fromstring(raw)
        channel = root.find("channel")
        if channel is None:
            atom_ns = "http://www.w3.org/2005/Atom"
            entries = root.findall(f"{{{atom_ns}}}entry") or root.findall("entry")
            for entry in entries[:max_items]:
                def get_text(tag):
                    el = entry.find(f"{{{atom_ns}}}{tag}") or entry.find(tag)
                    return (el.text or "").strip() if el is not None else ""
                title = get_text("title")
                link_el = entry.find(f"{{{atom_ns}}}link") or entry.find("link")
                link = (link_el.get("href") or link_el.text or "").strip() if link_el is not None else ""
                pub = get_text("updated") or get_text("published")
                if title and link:
                    items.append({"title": title, "link": link, "pub": pub, "description": ""})
        else:
            for item in channel.findall("item")[:max_items]:
                def _t(tag):
                    el = item.find(tag)
                    return (el.text or "").strip() if el is not None else ""
                title = _t("title")
                link = _t("link") or _t("guid")
                pub = _t("pubDate")
                desc = _t("description")
                if title and link:
                    items.append({"title": title, "link": link, "pub": pub, "description": desc})
    except Exception as e:
        print(f"  [WEB SCRAPER] RSS parse error {feed_url}: {e}")
    return items


def _resolve_google_news_url(gnews_url):
    if "news.google.com" not in gnews_url:
        return gnews_url
    try:
        r = requests.get(gnews_url, headers=SCRAPE_HEADERS, timeout=10, allow_redirects=True)
        return r.url
    except Exception:
        return gnews_url


def fetch_web_news(category="mixed", processed_ids=None, global_story_fps=None, limit=20, max_hours_old=72):
    """
    Fetches trending news from public RSS feeds for the given category.
    Returns list of post dicts compatible with ingestion.py format.
    """
    processed_ids = processed_ids or []
    global_story_fps = global_story_fps or []
    processed_set = set(str(x) for x in processed_ids)
    story_fp_set = set(str(x) for x in global_story_fps)

    feeds = CATEGORY_MAP.get(category.lower(), MIXED_RSS_FEEDS)
    now_ts = int(time.time())
    cutoff_ts = now_ts - (max_hours_old * 3600)

    print(f"  [WEB SCRAPER] Fetching {category.upper()} news from {len(feeds)} RSS feeds...")

    raw_articles = []
    seen_links = set()

    for feed_url in feeds:
        articles = _parse_rss_feed(feed_url, max_items=10)
        for art in articles:
            link = art["link"]
            if link in seen_links:
                continue
            seen_links.add(link)
            raw_articles.append(art)

    print(f"  [WEB SCRAPER] Found {len(raw_articles)} raw articles. Filtering and enriching...")

    results = []
    enriched = 0

    skip_keywords = ["best vpn", "how to watch", "sign up", "free trial", "subscribe", "coupon", "deal", "ranked", "every episode"]

    for art in raw_articles:
        if len(results) >= limit:
            break

        title = art["title"].strip()
        raw_link = art["link"].strip()
        pub_ts = _parse_pub_date(art["pub"])

        if pub_ts > 0 and pub_ts < cutoff_ts:
            continue
        if len(title) < 15:
            continue
        if any(kw in title.lower() for kw in skip_keywords):
            continue

        cap_fp = _caption_fingerprint(title)
        story_fp = _story_fingerprint(title)

        if cap_fp in processed_set or story_fp in story_fp_set:
            continue

        article_url = _resolve_google_news_url(raw_link)
        post_id = "web_" + hashlib.md5(article_url.encode("utf-8")).hexdigest()[:16]
        if post_id in processed_set:
            continue

        img_url = _fetch_og_image(article_url)
        if not img_url:
            desc = art.get("description", "")
            m = re.search(r'<img[^>]+src=["\x27]([^"\x27]+\.(?:jpg|jpeg|png|webp))["\x27]', desc)
            if m:
                img_url = m.group(1)

        if not img_url:
            continue

        if not _validate_image_url(img_url):
            continue

        enriched += 1
        effective_ts = pub_ts if pub_ts > 0 else (now_ts - 3600)

        results.append({
            "post_id": post_id,
            "photo_id": post_id,
            "caption_fingerprint": cap_fp,
            "story_fingerprint": story_fp,
            "caption": title,
            "image_url": img_url,
            "created_time": effective_ts,
            "source_tag": "Web News",
            "source_url": article_url,
            "is_web_source": True,
        })

    results.sort(key=lambda p: p.get("created_time", 0), reverse=True)
    print(f"  [WEB SCRAPER] Enriched {enriched} articles with valid images - returning {len(results)} posts.")
    return results


def get_channel_category(channel_name):
    """Map a channel name to a content category for RSS sourcing."""
    name = channel_name.lower()
    if any(k in name for k in ["hollywood", "movie", "film", "cinema"]):
        return "hollywood"
    if any(k in name for k in ["netflix", "streaming", "music", "anisha"]):
        return "netflix"
    return "mixed"
