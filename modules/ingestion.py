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

def fetch_facebook_public_posts(page_url_or_slug: str, processed_ids: list = None, limit: int = 5):
    """Scrapes and extracts real public posts from any public Facebook page (e.g. netflixfanslivehere)."""
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
    seen_posts = set()

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

                        if msg and len(msg.strip()) > 10 and photo_id:
                            raw_pid = str(p_id or photo_id)
                            if raw_pid not in seen_posts and raw_pid not in processed_ids:
                                seen_posts.add(raw_pid)
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

def fetch_source_posts(source_page_id: str, access_token: str, processed_ids: list, limit: int = 2, source_url: str = ""):
    processed_ids = processed_ids or []
    target = source_url or source_page_id

    if target:
        fb_posts = fetch_facebook_public_posts(target, processed_ids=processed_ids, limit=limit)
        if fb_posts:
            print(f" [FB INGEST] Retrieved {len(fb_posts)} real post(s) from Facebook page '{target}'")
            return fb_posts

    if access_token and access_token not in ["SIMULATED_DEMO_TOKEN", ""]:
        ident = extract_identifier(target)
        url = f"https://graph.facebook.com/v19.0/{ident}/posts"
        params = {
            "fields": "id,message,created_time,full_picture,attachments{media,subattachments}",
            "limit": 10,
            "access_token": access_token
        }
        try:
            res = requests.get(url, params=params, timeout=15)
            data = res.json()
            if "data" in data and len(data["data"]) > 0:
                new_posts = []
                for item in data["data"]:
                    p_id = item.get("id")
                    if p_id in processed_ids:
                        continue
                    img_url = item.get("full_picture")
                    caption = item.get("message", "")
                    if img_url:
                        new_posts.append({
                            "post_id": p_id,
                            "image_url": img_url,
                            "caption": caption,
                            "source_gap_hours": 2.0
                        })
                        if len(new_posts) >= limit:
                            break
                if new_posts:
                    return new_posts
        except Exception as e:
            print(f" [GRAPH API ERROR] {e}")

    return []
