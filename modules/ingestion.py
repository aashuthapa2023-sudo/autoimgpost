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

    # 2. Main pass: Strictly extract stories guaranteeing 1:1 caption & photo pairing
    def _decode_fb_id(raw):
        if not raw: return ""
        s_raw = str(raw).strip()
        if s_raw.startswith("Uzpf"):
            import base64
            try:
                dec = base64.b64decode(s_raw).decode('utf-8', errors='ignore')
                nums = re.findall(r'\d{9,18}', dec)
                if nums: return nums[-1]
            except Exception:
                pass
        return s_raw

    def extract_single_story(story_node):
        """
        Extracts post_id, message, photo_id, and image_url STRICTLY from this single story node.
        Guarantees 100% that caption and image belong to each other and NEVER cross-contaminate.
        """
        if not isinstance(story_node, dict):
            return None

        # 1. Message text directly belonging to THIS story
        msg = None
        if "message" in story_node and isinstance(story_node["message"], dict) and "text" in story_node["message"]:
            msg = story_node["message"]["text"].strip()
        elif "story" in story_node and isinstance(story_node["story"], dict):
            st = story_node["story"]
            if "message" in st and isinstance(st["message"], dict) and "text" in st["message"]:
                msg = st["message"]["text"].strip()

        if not msg or len(msg) < 8:
            return None

        # 2. Post ID
        raw_pid = story_node.get("post_id") or story_node.get("id") or ""
        pid_str = _decode_fb_id(raw_pid)

        # 3. Photo ID and Image URI strictly from THIS story's direct attachments
        photo_id = None
        img_url = None

        atts = story_node.get("attachments", [])
        if isinstance(atts, list):
            for a in atts:
                if not isinstance(a, dict):
                    continue
                styles_att = a.get("styles", {}).get("attachment", {}) if isinstance(a.get("styles"), dict) else {}
                med = styles_att.get("media") or a.get("media") or a.get("target") or {}
                if isinstance(med, dict):
                    if med.get("id"):
                        photo_id = str(med["id"])
                    img_obj = med.get("image") or med.get("photo_image") or {}
                    if isinstance(img_obj, dict) and img_obj.get("uri"):
                        img_url = img_obj["uri"]
                if photo_id:
                    break

        if not photo_id and story_node.get("photo_id"):
            photo_id = str(story_node["photo_id"])

        # Construct high-resolution crawler lookaside URI
        if photo_id:
            img_url = f"https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id={photo_id}"
        elif not img_url:
            # Text-only or video-only story without photo — skip to prevent pairing with unrelated photos!
            return None

        final_pid = pid_str or photo_id
        if not final_pid:
            return None

        created_time = post_meta.get(final_pid, 0)
        if not created_time and photo_id:
            created_time = post_meta.get(photo_id, 0)
        if not created_time:
            created_time = story_node.get("creation_time") or story_node.get("publish_time") or 0

        cap_fp = hashlib.md5(re.sub(r'\s+', '', msg[:60]).lower().encode('utf-8')).hexdigest()

        return {
            "post_id": str(final_pid),
            "photo_id": str(photo_id or final_pid),
            "caption_fingerprint": cap_fp,
            "caption": msg,
            "image_url": img_url,
            "created_time": int(created_time) if created_time else 0,
            "source_gap_hours": 2.0
        }

    posts_dict = {}
    processed_set = set(str(x) for x in processed_ids)

    for s in scripts:
        if '"message"' not in s and '"creation_time"' not in s and '"timeline_list_feed_units"' not in s:
            continue
        try:
            data = json.loads(s)
        except Exception:
            continue

        def scan_story_nodes(node):
            if isinstance(node, dict):
                # Check for standard feed story containers
                if "comet_sections" in node and isinstance(node["comet_sections"], dict):
                    content = node["comet_sections"].get("content", {})
                    if isinstance(content, dict) and "story" in content and isinstance(content["story"], dict):
                        st = extract_single_story(content["story"])
                        if st:
                            pid = st["post_id"]
                            phid = st["photo_id"]
                            fp = st["caption_fingerprint"]
                            if pid not in processed_set and phid not in processed_set and fp not in processed_set:
                                if pid not in posts_dict:
                                    posts_dict[pid] = st
                                    return

                # Check direct story node with message and attachments
                if ("message" in node and "attachments" in node) or (node.get("__typename") in ["Story", "CometFeedStoryDefaultContentStrategy"]):
                    st = extract_single_story(node)
                    if st:
                        pid = st["post_id"]
                        phid = st["photo_id"]
                        fp = st["caption_fingerprint"]
                        if pid not in processed_set and phid not in processed_set and fp not in processed_set:
                            if pid not in posts_dict:
                                posts_dict[pid] = st
                                return

                for v in node.values():
                    scan_story_nodes(v)
            elif isinstance(node, list):
                for it in node:
                    scan_story_nodes(it)

        scan_story_nodes(data)

    posts = list(posts_dict.values())
    posts.sort(key=lambda p: p.get("created_time", 0), reverse=True)
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
        per_source_limit = max(5, limit // max(1, len(targets)))
        fb_posts = fetch_facebook_public_posts(target, processed_ids=list(seen_ids), limit=per_source_limit)
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

    if all_posts:
        # Sort aggregated posts across all sources strictly by created_time descending
        all_posts.sort(key=lambda p: p.get("created_time", 0), reverse=True)
        print(f" [MULTI-SOURCE INGEST] Retrieved {len(all_posts)} post(s) from {len(targets)} source page(s)")
        return all_posts[:max(limit, 30)]

    return []
