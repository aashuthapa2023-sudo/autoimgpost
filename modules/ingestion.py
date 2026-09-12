import os
import json
import re
import hashlib
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

    # 1. Pre-pass: Extract true post_id -> publish_time (integer) from tracking strings and metadata
    post_meta = {}
    for m in re.finditer(r'\\?"publish_time\\?":\s*(\d{9,11}).*?\\"story_fbid\\":\[\\"(\d+)\\"\]', html):
        ts = int(m.group(1))
        fbid = str(m.group(2))
        post_meta[fbid] = ts

    for m in re.finditer(r'\\"story_fbid\\":\[\\"(\d+)\\"\\].*?\\"publish_time\\":\s*(\d{9,11})', html):
        fbid = str(m.group(1))
        ts = int(m.group(2))
        post_meta[fbid] = ts

    for s in scripts:
        if '"publish_time"' not in s and '"creation_time"' not in s:
            continue
        try:
            data = json.loads(s)
            def scan_nodes(node):
                if isinstance(node, dict):
                    pid = str(node.get("post_id") or node.get("id") or "")
                    ts = node.get("creation_time") or node.get("publish_time")
                    if not ts and "tracking" in node:
                        tm = re.search(r'\\?"publish_time\\?":\s*(\d{9,11})', str(node.get("tracking")))
                        if tm:
                            ts = int(tm.group(1))
                    if pid and ts:
                        post_meta[pid] = int(ts)
                    for v in node.values():
                        scan_nodes(v)
                elif isinstance(node, list):
                    for it in node:
                        scan_nodes(it)
            scan_nodes(data)
        except Exception:
            pass

    # 2. Main pass: Extract stories and attach accurate timestamps and master images
    def _decode_fb_id(raw):
        if not raw: return ""
        s_raw = str(raw).strip()
        if s_raw.startswith("Uzpf"):
            try:
                import base64
                dec = base64.b64decode(s_raw).decode('utf-8', errors='ignore')
                nums = re.findall(r'\d{9,18}', dec)
                if nums: return nums[-1]
            except Exception:
                pass
        return s_raw

    posts_dict = {}

    for s in scripts:
        if ('"message"' not in s and '"story"' not in s and '"creation_time"' not in s):
            continue
        try:
            data = json.loads(s)

            def extract_stories(node, parent_pid="", parent_ts=0):
                if isinstance(node, dict):
                    node_pid = _decode_fb_id(node.get("post_id") or node.get("id") or "")
                    cur_pid = node_pid or parent_pid
                    cur_ts = post_meta.get(cur_pid) or node.get("creation_time") or parent_ts or 0

                    msg = None
                    if "message" in node and isinstance(node["message"], dict) and "text" in node["message"]:
                        msg = node["message"]["text"].strip()
                    elif "story" in node and isinstance(node["story"], dict):
                        st = node["story"]
                        if "message" in st and isinstance(st["message"], dict):
                            msg = st["message"].get("text", "").strip()

                    if msg and len(msg) > 8:
                        media_id = None
                        img_url = None

                        # 1. Check direct attachments
                        atts = node.get("attachments", [])
                        if isinstance(atts, list):
                            for a in atts:
                                if isinstance(a, dict):
                                    med = a.get("media") or a.get("target")
                                    if isinstance(med, dict) and med.get("id"):
                                        media_id = str(med["id"])
                                        break
                                s_a = json.dumps(a)
                                att_uris = [
                                    bytes(u, "utf-8").decode("unicode_escape", errors="ignore").replace("\\/", "/")
                                    for u in re.findall(r'"uri":\s*"([^"]+)"', s_a)
                                    if "rsrc.php" not in u and "static.xx" not in u and ("fbcdn.net" in u or "scontent" in u)
                                ]
                                if att_uris and not img_url:
                                    img_url = att_uris[0]

                        # 2. Check direct media_id or photo_id
                        if not media_id:
                            if node.get("photo_id"):
                                media_id = str(node["photo_id"])
                            elif node.get("media_id"):
                                media_id = str(node["media_id"])
                            else:
                                s_sub = json.dumps(node)
                                pm = re.search(r'"Photo",\s*"id":\s*"(\d+)"', s_sub) or re.search(r'"photo_id":\s*"(\d+)"', s_sub)
                                if pm:
                                    media_id = pm.group(1)

                        # 3. Direct high-resolution crawler lookaside URI
                        if not img_url and media_id:
                            img_url = f"https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id={media_id}"

                        if not cur_ts and media_id:
                            cur_ts = post_meta.get(str(media_id), 0)
                        if not cur_ts and "tracking" in node:
                            tm = re.search(r'\\?"publish_time\\?":\s*(\d{9,11})', str(node.get("tracking")))
                            if tm: cur_ts = int(tm.group(1))

                        clean_k = re.sub(r'\s+', ' ', msg[:50])
                        cap_fp = hashlib.md5(re.sub(r'\s+', '', msg[:60]).lower().encode('utf-8')).hexdigest()
                        effective_pid = cur_pid or media_id
                        processed_set = set(str(x) for x in processed_ids)

                        is_already_posted = (
                            str(effective_pid) in processed_set or
                            str(media_id) in processed_set or
                            cap_fp in processed_set
                        )

                        if not is_already_posted and (media_id or img_url):
                            key = effective_pid or media_id
                            if key not in posts_dict:
                                posts_dict[key] = {
                                    "post_id": str(effective_pid),
                                    "photo_id": str(media_id or effective_pid),
                                    "caption_fingerprint": cap_fp,
                                    "caption": msg,
                                    "image_url": img_url,
                                    "created_time": int(cur_ts) if cur_ts else 0,
                                    "source_gap_hours": 2.0
                                }
                            else:
                                if cur_ts > posts_dict[key]["created_time"]:
                                    posts_dict[key]["created_time"] = int(cur_ts)
                                if effective_pid and not posts_dict[key]["post_id"]:
                                    posts_dict[key]["post_id"] = str(effective_pid)
                                if img_url and not posts_dict[key]["image_url"]:
                                    posts_dict[key]["image_url"] = img_url

                    for v in node.values():
                        extract_stories(v, cur_pid, cur_ts)
                elif isinstance(node, list):
                    for it in node:
                        extract_stories(it, parent_pid, parent_ts)

            extract_stories(data)
        except Exception:
            pass

    posts = list(posts_dict.values())
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
            pid = str(p.get("post_id", ""))
            photo_id = str(p.get("photo_id", ""))
            cap_fp = str(p.get("caption_fingerprint", ""))
            if pid not in seen_ids and photo_id not in seen_ids and cap_fp not in seen_ids:
                if pid: seen_ids.add(pid)
                if photo_id: seen_ids.add(photo_id)
                if cap_fp: seen_ids.add(cap_fp)
                p["source_tag"] = extract_identifier(target).replace("_", " ").title()
                all_posts.append(p)
                if len(all_posts) >= limit:
                    break

    if all_posts:
        print(f" [MULTI-SOURCE INGEST] Retrieved {len(all_posts)} post(s) from {len(targets)} source page(s)")
        return all_posts

    return []
