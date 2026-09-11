import os
import json
import re
import requests
from datetime import datetime, timezone

FB_BOT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.facebook.com/'
}

def extract_identifier(url_or_id: str) -> str:
    url = url_or_id.strip()
    if not url.startswith("http"):
        return url.replace('@', '').rstrip('/')

    # Direct post links
    if '/posts/' in url:
        return url
    if 'story_fbid' in url or 'fbid=' in url or '/photo' in url:
        return url

    id_match = re.search(r'[?&]id=(\d+)', url)
    if id_match:
        return id_match.group(1)

    pages_match = re.search(r'/pages/[^/]+/(\d+)', url)
    if pages_match:
        return pages_match.group(1)

    slug_match = re.search(r'facebook\.com/(?:pages/)?([a-zA-Z0-9._-]+)', url)
    if slug_match and slug_match.group(1).lower() not in ['watch', 'share', 'photo', 'groups', 'login', 'p']:
        return slug_match.group(1)

    return url

def fetch_facebook_public_posts(page_url_or_slug: str, processed_ids: list = None, limit: int = 15):
    """
    Universally scrapes and extracts real-time posts from ANY public Facebook URL
    (page URLs, direct post links, profile IDs, or slugs) using Googlebot SSR routing.
    """
    processed_ids = processed_ids or []
    target = page_url_or_slug.strip()
    if target.startswith("http"):
        url = target
    else:
        ident = extract_identifier(target)
        url = f"https://www.facebook.com/{ident}"

    try:
        res = requests.get(url, headers=FB_BOT_HEADERS, timeout=20)
    except Exception as e:
        print(f" [FB INGEST ERROR] Network request to {url} failed: {e}")
        return []

    if res.status_code != 200:
        print(f" [FB INGEST ERROR] Facebook URL {url} returned HTTP {res.status_code}")
        return []

    html = res.text
    scripts = re.findall(r'<script\s+type="application/json"[^>]*>(.*?)</script>', html)

    posts = []
    seen = set()

    for s in scripts:
        if ('"message"' not in s and '"story"' not in s and '"creation_time"' not in s):
            continue
        try:
            data = json.loads(s)

            def walk(node):
                if isinstance(node, dict):
                    msg = None
                    if "message" in node and isinstance(node["message"], dict) and "text" in node["message"]:
                        msg = node["message"]["text"]
                    elif "story" in node and isinstance(node["story"], dict):
                        st = node["story"]
                        if "message" in st and isinstance(st["message"], dict):
                            msg = st["message"].get("text")

                    if msg and len(msg.strip()) > 8:
                        s_sub = json.dumps(node)

                        # Extract photo_id or media_id
                        photo_id = None
                        pm = re.search(r'"photo_id":\s*"(\\d+)"', s_sub)
                        if pm:
                            photo_id = pm.group(1)
                        if not photo_id:
                            pm2 = re.search(r'media_id=(\\d+)', s_sub)
                            if pm2:
                                photo_id = pm2.group(1)

                        img_url = None
                        if photo_id:
                            img_url = f"https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id={photo_id}"
                        else:
                            # Direct high-res CDN uri
                            um = re.search(r'"uri":\s*"(https://scontent[^"]+)"', s_sub)
                            if um:
                                img_url = bytes(um.group(1), "utf-8").decode("unicode_escape", errors="ignore").replace("\\/", "/")

                        # Post ID
                        p_id = node.get("post_id") or node.get("id") or photo_id

                        # Timestamp
                        ts = node.get("creation_time") or node.get("publish_time")
                        if not ts:
                            tm = re.search(r'"(?:publish_time|creation_time)":\s*(\\d{9,11})', s_sub)
                            if tm:
                                ts = int(tm.group(1))

                        if img_url:
                            clean_k = re.sub(r'\s+', ' ', msg.strip()[:50])
                            raw_pid = str(p_id or photo_id or len(posts) + 1)
                            if clean_k not in seen and raw_pid not in processed_ids:
                                seen.add(clean_k)
                                posts.append({
                                    "post_id": raw_pid,
                                    "photo_id": photo_id or "cdn_photo",
                                    "caption": msg.strip(),
                                    "image_url": img_url,
                                    "created_time": int(ts) if ts else int(datetime.now(timezone.utc).timestamp()),
                                    "source_gap_hours": 2.0
                                })

                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for it in node:
                        walk(it)

            walk(data)
        except Exception:
            pass

    # Sort strictly by timestamp descending so the newest, real-time posts are always first!
    posts.sort(key=lambda p: p.get("created_time", 0), reverse=True)

    # Calculate gap hours between successive posts
    for i in range(len(posts) - 1):
        t1 = posts[i].get("created_time")
        t2 = posts[i + 1].get("created_time")
        if t1 and t2:
            gap = max(1.0, round(abs(t1 - t2) / 3600.0, 2))
            posts[i]["source_gap_hours"] = gap

    return posts[:limit]

def fetch_source_posts(source_page_id: str = "", access_token: str = "", processed_ids: list = None, limit: int = 2, source_url: str = "", source_pages: list = None, **kwargs):
    """
    Fetches posts across MULTIPLE source Facebook pages configured for a destination channel.
    """
    if "page_id" in kwargs and not source_page_id:
        source_page_id = kwargs["page_id"]
    if "source_urls" in kwargs and not source_pages:
        source_pages = kwargs["source_urls"]

    processed_ids = processed_ids or []
    targets = []

    if source_pages and isinstance(source_pages, list):
        for sp in source_pages:
            if sp and sp not in targets:
                targets.append(sp)

    if source_url and source_url not in targets:
        targets.append(source_url)
    if not targets and source_page_id:
        targets.append(source_page_id)

    all_posts = []
    seen_ids = set(processed_ids)

    for target in targets:
        if len(all_posts) >= limit:
            break
        needed = limit - len(all_posts)
        fb_posts = fetch_facebook_public_posts(target, processed_ids=list(seen_ids), limit=needed)
        for p in fb_posts:
            pid = p["post_id"]
            if pid not in seen_ids:
                seen_ids.add(pid)
                p["source_tag"] = extract_identifier(target).replace("_", " ").title()
                all_posts.append(p)
                if len(all_posts) >= limit:
                    break

    if all_posts:
        print(f" [MULTI-SOURCE INGEST] Retrieved {len(all_posts)} post(s) from {len(targets)} source page(s)")
        return all_posts

    return []
