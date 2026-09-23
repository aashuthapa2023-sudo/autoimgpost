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

def parse_relative_time(time_str: str) -> int:
    import time
    now = int(time.time())
    if not time_str:
        return now
    s = time_str.strip().lower()
    if 'just now' in s or 'now' in s:
        return now
    m = re.search(r'(\d+)\s*m', s)
    if m:
        return now - int(m.group(1)) * 60
    h = re.search(r'(\d+)\s*h', s)
    if h:
        return now - int(h.group(1)) * 3600
    d = re.search(r'(\d+)\s*d', s)
    if d:
        return now - int(d.group(1)) * 86400
    return now

def fetch_facebook_mobile_playwright(page_url_or_slug: str, processed_ids: list = None, limit: int = 15):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    ident = extract_identifier(page_url_or_slug)
    mobile_url = f"https://m.facebook.com/{ident}"
    processed_set = set(str(x) for x in (processed_ids or []))
    print(f" [PLAYWRIGHT FB] Ingesting {mobile_url} via mobile Chromium bypass...")

    posts = []
    try:
        with sync_playwright() as p:
            iphone = p.devices['iPhone 13']
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(**iphone)
            page = context.new_page()
            page.goto(mobile_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)

            cards = page.evaluate('''() => {
                const results = [];
                const imgs = Array.from(document.querySelectorAll('img[src*="/v/t39.30808-6/"]'));
                imgs.forEach(img => {
                    const src = img.src;
                    const m = src.match(/\\/v\\/t39\\.30808-6\\/\\d+_(\\d{14,18})_/);
                    if (!m) return;
                    const photoId = m[1];
                    if ((img.alt && (img.alt.includes('Cover') || img.alt.includes('profile'))) || img.naturalWidth < 150) return;

                    let cur = img;
                    let postContainer = img.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (!cur || cur === document.body) break;
                        if (cur.querySelectorAll('img[src*="/v/t39.30808-6/"]').length > 1) {
                            break; // Stop: multi-post container reached, do not escape this post boundary
                        }
                        postContainer = cur;
                        if (cur.getAttribute('role') === 'article' || cur.tagName.toLowerCase() === 'article') {
                            break; // Post card boundary identified
                        }
                        cur = cur.parentElement;
                    }

                    let text = "";
                    let timeStr = "";
                    const tEls = (postContainer || img.parentElement).querySelectorAll('span, div, p');
                    for (const el of tEls) {
                        let t = (el.innerText || "").trim();
                        if (!timeStr) {
                            const tm = t.match(/^(\\d+[mhdw]|Just now)$/i);
                            if (tm) timeStr = tm[1];
                        }
                        t = t.replace(/\\.\\.\\.\\s*See\\s*more/gi, '').replace(/See\\s*more/gi, '').trim();
                        if (/[\\u0900-\\u097F]{4,}/.test(t) && t.length > 25) {
                            if (!t.includes("Himali Patrika") && !t.includes("News & media website") && !t.includes("others") && !t.includes("Abhi Raj")) {
                                if (t.length > text.length && t.length < 600) {
                                    text = t;
                                }
                            }
                        }
                    }
                    results.push({
                        photoId: photoId,
                        imgUrl: src,
                        caption: text,
                        timeStr: timeStr,
                        alt: img.alt || ""
                    });
                });
                return results;
            }''')
            browser.close()

        seen_pids = set()
        for c in cards:
            pid = c.get("photoId")
            cap = c.get("caption", "").strip()
            if not cap and c.get("alt"):
                alt_m = re.findall(r'[\u0900-\u097F]{4,}', c.get("alt"))
                if len(alt_m) >= 2:
                    cap = re.sub(r'^May be an image of [^\n\']*(?:text that says)?[\'"]?', '', c.get("alt")).strip().rstrip("'\"")

            if not pid or pid in seen_pids or pid in processed_set or len(cap) < 15:
                continue
            seen_pids.add(pid)

            created_ts = parse_relative_time(c.get("timeStr", ""))
            cap_fp = hashlib.md5(re.sub(r'\s+', '', cap[:60]).lower().encode('utf-8')).hexdigest()
            if cap_fp in processed_set:
                continue

            posts.append({
                "post_id": pid,
                "photo_id": pid,
                "caption_fingerprint": cap_fp,
                "caption": cap,
                "image_url": c.get("imgUrl"),
                "created_time": created_ts,
                "source_gap_hours": 0.25,
                "source_tag": "Himali Patrika"
            })
            if len(posts) >= limit:
                break
    except Exception as e:
        print(f" [PLAYWRIGHT FB ERROR] Error scraping {mobile_url}: {e}")

    return posts

def fetch_facebook_public_posts(page_url_or_slug: str, processed_ids: list = None, limit: int = 15):
    """
    Universally scrapes and extracts real-time posts from ANY public Facebook URL
    (page URLs, direct post links, profile IDs, or slugs) using Googlebot SSR routing with Playwright fallback.
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
        print(f" [FB INGEST ERROR] Network request to {url} failed: {e}. Trying Playwright fallback...")
        return fetch_facebook_mobile_playwright(page_url_or_slug, processed_ids=processed_ids, limit=limit)

    if res.status_code != 200 or "facebook.com/login" in res.url.lower():
        print(f" [FB INGEST] URL {url} redirected to login or returned {res.status_code}. Engaging Playwright mobile bypass...")
        pw_posts = fetch_facebook_mobile_playwright(page_url_or_slug, processed_ids=processed_ids, limit=limit)
        if pw_posts:
            return pw_posts
        return []

    html = res.text
    scripts = re.findall(r'<script\s+type="application/json"[^>]*>(.*?)</script>', html)
    if len(scripts) < 3:
        print(f" [FB INGEST] Insufficient JSON scripts ({len(scripts)}) on {url}. Engaging Playwright mobile bypass...")
        pw_posts = fetch_facebook_mobile_playwright(page_url_or_slug, processed_ids=processed_ids, limit=limit)
        if pw_posts:
            return pw_posts

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

        def _find_img_in_node(node):
            if not isinstance(node, dict):
                return None
            for k in ["large_share_image", "flexible_height_share_image", "image", "photo_image", "preview_image"]:
                val = node.get(k)
                if isinstance(val, dict) and val.get("uri") and str(val["uri"]).startswith("http"):
                    return str(val["uri"])
            for med_k in ["media", "target", "attachment"]:
                med = node.get(med_k)
                if isinstance(med, dict):
                    res = _find_img_in_node(med)
                    if res:
                        return res
            styles = node.get("styles")
            if isinstance(styles, dict):
                res = _find_img_in_node(styles)
                if res:
                    return res
            sub = node.get("subattachments") or node.get("all_subattachments")
            if isinstance(sub, dict) and "nodes" in sub:
                for sn in sub["nodes"]:
                    res = _find_img_in_node(sn)
                    if res:
                        return res
            return None

        atts = story_node.get("attachments", [])
        if isinstance(atts, list):
            for a in atts:
                if not isinstance(a, dict):
                    continue
                if not img_url:
                    img_url = _find_img_in_node(a)
                styles_att = a.get("styles", {}).get("attachment", {}) if isinstance(a.get("styles"), dict) else {}
                med = styles_att.get("media") or a.get("media") or a.get("target") or {}
                if isinstance(med, dict) and med.get("id"):
                    mid = str(med["id"])
                    if mid.isdigit() and len(mid) >= 9:
                        photo_id = mid

        if not photo_id and story_node.get("photo_id"):
            raw_phid = str(story_node["photo_id"])
            if raw_phid.isdigit():
                photo_id = raw_phid

        # Construct crawler lookaside URI only as fallback for genuine numeric photo IDs
        if photo_id and not img_url:
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
        if not created_time or int(created_time) <= 0:
            import time
            created_time = int(time.time()) - 1800

        cap_fp = hashlib.md5(re.sub(r'\s+', '', msg[:60]).lower().encode('utf-8')).hexdigest()

        return {
            "post_id": str(final_pid),
            "photo_id": str(photo_id or final_pid),
            "caption_fingerprint": cap_fp,
            "caption": msg,
            "image_url": img_url,
            "created_time": int(created_time),
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

    if not posts_dict:
        print(f" [FB INGEST] Standard SSR yielded 0 posts for {url}. Engaging Playwright mobile bypass...")
        pw_posts = fetch_facebook_mobile_playwright(page_url_or_slug, processed_ids=processed_ids, limit=limit)
        if pw_posts:
            return pw_posts

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
    seen_ids = set(str(x) for x in processed_ids if x)

    for target in targets:
        per_source_limit = max(15, limit)
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
