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
    url_or_id = url_or_id.strip()
    id_match = re.search(r'[?&]id=(\d+)', url_or_id)
    if id_match:
        return id_match.group(1)
    pages_match = re.search(r'/pages/[^/]+/(\d+)', url_or_id)
    if pages_match:
        return pages_match.group(1)
    slug_match = re.search(r'facebook\.com/(?:pages/)?([a-zA-Z0-9._-]+)', url_or_id)
    if slug_match and slug_match.group(1).lower() not in ['watch', 'share', 'photo', 'groups', 'login']:
        return slug_match.group(1)
    return url_or_id.replace('@', '').rstrip('/')

def fetch_facebook_public_posts(page_url_or_slug: str, processed_ids: list = None, limit: int = 15):
    """
    Scrapes and extracts up to 25 real public posts from any public Facebook page
    (e.g., https://www.facebook.com/netflixfanslivehere) using Googlebot SSR routing.
    """
    processed_ids = processed_ids or []
    ident = extract_identifier(page_url_or_slug)
    url = f"https://www.facebook.com/{ident}"

    try:
        res = requests.get(url, headers=FB_BOT_HEADERS, timeout=20)
    except Exception as e:
        print(f" [FB INGEST ERROR] Network request to {url} failed: {e}")
        return []

    if res.status_code != 200:
        print(f" [FB INGEST ERROR] Facebook page {url} returned HTTP {res.status_code}")
        return []

    html = res.text
    scripts = re.findall(r'<script\s+type="application/json"[^>]*>(.*?)</script>', html)

    posts = []
    seen = set()

    for s in scripts:
        if ('creation_time' not in s and 'publish_time' not in s) or ('message' not in s and 'story' not in s):
            continue
        try:
            data = json.loads(s)

            def walk(node):
                if isinstance(node, dict):
                    story = None
                    if "story" in node and isinstance(node["story"], dict):
                        story = node["story"]
                    elif "message" in node and isinstance(node.get("message"), dict) and "text" in node["message"]:
                        story = node

                    if story:
                        msg = ""
                        if "message" in story and isinstance(story["message"], dict):
                            msg = story["message"].get("text", "")

                        p_id = story.get("post_id") or story.get("id")
                        if not p_id and "tracking" in story and isinstance(story["tracking"], str):
                            try:
                                tr = json.loads(story["tracking"])
                                p_id = tr.get("top_level_post_id") or tr.get("mf_story_key")
                            except Exception:
                                pass

                        photo_id = None
                        s_sub = json.dumps(story)
                        pm = re.search(r'"photo_id":\s*"(\d+)"', s_sub)
                        if pm:
                            photo_id = pm.group(1)
                        if not photo_id:
                            pm2 = re.search(r'media_id=(\d+)', s_sub)
                            if pm2:
                                photo_id = pm2.group(1)

                        created_ts = story.get("creation_time") or story.get("publish_time")
                        if not created_ts:
                            tm = re.search(r'"publish_time":\s*(\d{9,11})', s_sub)
                            if tm:
                                created_ts = int(tm.group(1))

                        if msg and len(msg.strip()) > 10:
                            if not photo_id:
                                any_media = re.findall(r'media_id=(\d+)', s_sub)
                                if any_media:
                                    photo_id = any_media[0]

                            if photo_id:
                                clean_key = re.sub(r'\s+', ' ', msg.strip()[:60])
                                raw_pid = str(p_id or photo_id)
                                if clean_key not in seen and raw_pid not in processed_ids:
                                    seen.add(clean_key)
                                    posts.append({
                                        "post_id": raw_pid,
                                        "photo_id": photo_id,
                                        "caption": msg.strip(),
                                        "image_url": f"https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id={photo_id}",
                                        "created_time": created_ts or int(datetime.now(timezone.utc).timestamp()),
                                        "source_gap_hours": 2.0
                                    })

                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for item in node:
                        walk(item)

            walk(data)
        except Exception:
            pass

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
