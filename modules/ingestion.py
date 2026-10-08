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

def facebook_mobile_url(url_or_id):
    """Preserve post/profile paths and queries when changing Facebook hostname."""
    from urllib.parse import urlsplit, urlunsplit
    target = str(url_or_id or '').strip()
    if target.startswith(('http://', 'https://')):
        parts = urlsplit(target)
        if (parts.hostname or '').lower() not in ('facebook.com', 'www.facebook.com', 'm.facebook.com', 'mbasic.facebook.com'):
            raise ValueError('Source URL must refer to Facebook')
        return urlunsplit(('https', 'm.facebook.com', parts.path or '/', parts.query, ''))
    return 'https://m.facebook.com/' + extract_identifier(target)


def _select_photo_from_attachment(attachment):
    """Return an image and its ID together; exclude video/link preview media."""
    if not isinstance(attachment, dict):
        return None
    kind = str(attachment.get('__typename') or '').lower()
    if any(blocked in kind for blocked in ('video', 'external', 'link')):
        return None
    if kind == 'story' or ('message' in attachment and kind != 'photo'):
        return None
    target = attachment.get('target')
    if isinstance(target, dict):
        target_kind = str(target.get('__typename') or '').lower()
        if target_kind and target_kind != 'photo':
            return None
    if kind == 'photo' or (not kind and attachment.get('id') and any(k in attachment for k in ('image', 'photo_image', 'large_image'))):
        photo_id = str(attachment.get('id') or '')
        if photo_id and not photo_id.isdigit():
            return None
        image_url = None
        for key in ('large_image', 'image', 'photo_image'):
            value = attachment.get(key)
            if isinstance(value, dict) and isinstance(value.get('uri'), str) and value['uri'].startswith(('http://', 'https://')):
                image_url = value['uri']
                break
        if image_url or photo_id:
            return photo_id, image_url
    for key in ('media', 'target', 'attachment'):
        selected = _select_photo_from_attachment(attachment.get(key))
        if selected:
            return selected
    styles = attachment.get('styles')
    if isinstance(styles, dict):
        selected = _select_photo_from_attachment(styles)
        if selected:
            return selected
    for key in ('subattachments', 'all_subattachments'):
        children = attachment.get(key)
        if isinstance(children, dict):
            children = children.get('nodes', [])
        if isinstance(children, list):
            for child in children:
                selected = _select_photo_from_attachment(child)
                if selected:
                    return selected
    return None


def _exact_story_caption(story):
    """Use this story's message, never a nested share or image ALT."""
    if not isinstance(story, dict):
        return ''
    message = story.get('message')
    if not isinstance(message, dict) or not isinstance(message.get('text'), str):
        return ''
    if any(message.get(flag) is True or story.get(flag) is True for flag in ('is_truncated', 'truncated', 'has_more')):
        return ''
    caption = message['text'].strip()
    if re.search(r'(?:\.\.\.|…)\s*(?:See\s+more|थप\s+हेर्नुहोस्)?\s*$', caption, re.IGNORECASE):
        return ''
    return caption


def _caption_fingerprint(caption):
    """Versioned full-message identity; a shared first line is not a duplicate."""
    normalized = re.sub(r'\s+', '', str(caption or '')).lower()
    return 'caption_v2_' + hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _page_identity(value):
    from urllib.parse import urlsplit, parse_qs
    target = str(value or '').strip().rstrip('/')
    if not target:
        return None
    if not target.startswith(('http://', 'https://')):
        return ('id', target) if target.isdigit() else ('slug', target.lstrip('@').casefold())
    parts = urlsplit(target)
    if (parts.hostname or '').lower() not in ('facebook.com', 'www.facebook.com', 'm.facebook.com', 'mbasic.facebook.com'):
        return None
    page_id = parse_qs(parts.query).get('id', [''])[0]
    if page_id.isdigit():
        return 'id', page_id
    segments = [segment for segment in parts.path.split('/') if segment]
    if not segments:
        return None
    if segments[0].lower() in ('people', 'pages') and segments[-1].isdigit():
        return 'id', segments[-1]
    if segments[0].lower() in ('photo', 'photos', 'photo.php', 'story.php', 'permalink.php', 'watch', 'groups', 'share', 'login'):
        return None
    return ('id', segments[0]) if segments[0].isdigit() else ('slug', segments[0].casefold())


def _story_matches_source(story, source_url):
    """Reject contradictory known authors; absence or aliases are not guessed."""
    expected = _page_identity(source_url)
    actors = story.get('actors') if isinstance(story, dict) else None
    if expected is None or not isinstance(actors, list) or not actors:
        return True
    comparable = []
    for actor in actors:
        if not isinstance(actor, dict):
            continue
        identities = [_page_identity(actor.get('url'))]
        if str(actor.get('id') or '').isdigit():
            identities.append(('id', str(actor['id'])))
        for identity in identities:
            if identity == expected:
                return True
            if identity and identity[0] == expected[0]:
                comparable.append(identity)
    return not comparable


def parse_relative_time(time_str: str) -> int:
    import time
    now = int(time.time())
    if not time_str:
        return 0
    s = str(time_str).strip().lower().translate(str.maketrans('०१२३४५६७८९', '0123456789'))
    if s in ('just now', 'now', 'अहिले'):
        return now
    m = re.fullmatch(r'(\d+)\s*(?:m|min|mins|minutes?|मिनेट)', s)
    if m:
        return now - int(m.group(1)) * 60
    h = re.fullmatch(r'(\d+)\s*(?:h|hr|hrs|hours?|घण्टा)', s)
    if h:
        return now - int(h.group(1)) * 3600
    d = re.fullmatch(r'(\d+)\s*(?:d|days?|दिन)', s)
    if d:
        return now - int(d.group(1)) * 86400
    w = re.fullmatch(r'(\d+)\s*(?:w|weeks?|हप्ता)', s)
    if w:
        return now - int(w.group(1)) * 604800
    return 0

def _posts_from_mobile_cards(cards, processed_ids=None, limit=15):
    """Accept only complete messages and verified photographs from one card."""
    posts = []
    seen = set(str(value) for value in processed_ids or [])
    for card in cards or []:
        if not isinstance(card, dict) or not all(card.get(flag) is True for flag in ('caption_verified', 'caption_complete', 'image_verified')):
            continue
        post_id = str(card.get('postId') or '')
        photo_id = str(card.get('photoId') or '')
        caption = str(card.get('caption') or '').strip()
        image_url = str(card.get('imgUrl') or '')
        if not post_id or not photo_id.isdigit() or post_id in seen or photo_id in seen or len(caption) < 8 or not image_url.startswith(('http://', 'https://')):
            continue
        if not _exact_story_caption({'message': {'text': caption}}):
            continue
        try:
            created_time = int(card.get('createdTime') or 0) or parse_relative_time(card.get('timeStr') or '')
        except (ValueError, TypeError):
            continue
        if created_time <= 0:
            continue
        fingerprint = _caption_fingerprint(caption)
        if fingerprint in seen:
            continue
        seen.update((post_id, photo_id, fingerprint))
        posts.append({'post_id': post_id, 'photo_id': photo_id, 'caption_fingerprint': fingerprint,
                      'caption': caption, 'image_url': image_url, 'created_time': created_time,
                      'source_gap_hours': 0.25})
        if len(posts) >= limit:
            break
    return posts


def fetch_facebook_mobile_playwright(page_url_or_slug: str, processed_ids: list = None, limit: int = 15):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    mobile_url = facebook_mobile_url(page_url_or_slug)
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

            # A browser may receive full hydration JSON even when its visible
            # mobile cards lack stable message selectors. Reuse the exact same
            # story/photo extractor; no DOM text guesses or ALT captions.
            hydrated_scripts = page.evaluate("() => Array.from(document.querySelectorAll('script[type=\"application/json\"]')).map(node => node.textContent || '')")
            resolved_url = getattr(page, 'url', '')
            expected_source = resolved_url if _page_identity(resolved_url) else page_url_or_slug
            hydrated_posts = _extract_facebook_story_posts(hydrated_scripts, processed_ids, limit, source_url=expected_source)
            if hydrated_posts:
                print(f" [PLAYWRIGHT FB] Retrieved {len(hydrated_posts)} exact caption/photo pairs from hydration JSON")
                browser.close()
                return hydrated_posts

            cards = page.evaluate(r'''() => {
                const results = [];
                const articles = Array.from(document.querySelectorAll('[role="article"], article'));
                const messageSelector = '[data-ad-preview="message"], [data-ad-comet-preview="message"], [data-testid="post_message"], .userContent';
                for (const article of articles) {
                    const messages = Array.from(article.querySelectorAll(messageSelector)).filter(el => el.closest('[role="article"], article') === article);
                    // A nested shared post or multiple different message fields is
                    // ambiguous. Never choose the longest descendant or image ALT.
                    const uniqueMessages = [...new Set(messages.map(el => (el.innerText || '').trim()).filter(Boolean))];
                    if (uniqueMessages.length !== 1) continue;
                    const caption = uniqueMessages[0];
                    const truncated = /(?:\.\.\.|…)\s*(?:See\s+more|थप\s+हेर्नुहोस्)?\s*$/i.test(caption) || messages.some(el => Array.from(el.querySelectorAll('a, [role="button"]')).some(control => /^(See more|थप हेर्नुहोस्)$/i.test((control.innerText || '').trim())));
                    if (truncated) continue;
                    if (article.querySelector('video, a[href*="/videos/"], a[href*="/watch/"]')) continue;
                    const photos = [];
                    for (const img of article.querySelectorAll('img')) {
                        if (img.closest('[role="article"], article') !== article || img.naturalWidth < 150) continue;
                        const src = img.currentSrc || img.src;
                        let parsed;
                        try { parsed = new URL(src); } catch (_) { continue; }
                        if (!/(?:fbcdn\.net|fbsbx\.com)$/.test(parsed.hostname)) continue;
                        const photoLink = img.closest('a[href]');
                        const href = photoLink ? photoLink.href : '';
                        if (!/\/photos?\b|[?&]fbid=/.test(href)) continue;
                        const photoMatch = href.match(/[?&]fbid=(\d+)/) || href.match(/\/photos\/(?:[^/?#]+\/)?(\d{9,20})/);
                        const photoId = photoMatch ? photoMatch[1] : '';
                        if (!photoId) continue;
                        if (!photos.some(photo => photo.photoId === photoId)) photos.push({photoId, imgUrl: src});
                    }
                    // DOM albums cannot establish which photograph a prose
                    // caption describes; SSR photo attachments remain supported.
                    if (photos.length !== 1) continue;
                    const timeElement = article.querySelector('time[datetime], [data-utime], abbr');
                    let createdTime = 0;
                    let timeStr = '';
                    if (timeElement) {
                        createdTime = Number(timeElement.getAttribute('data-utime') || 0);
                        if (!createdTime && timeElement.getAttribute('datetime')) createdTime = Math.floor(Date.parse(timeElement.getAttribute('datetime')) / 1000) || 0;
                        timeStr = (timeElement.innerText || '').trim();
                    }
                    const links = Array.from(article.querySelectorAll('a[href]'));
                    const postIds = [...new Set(links.map(link => {
                        const match = link.href.match(/[?&]story_fbid=([^&#]+)/) || link.href.match(/\/posts\/([^/?#]+)/);
                        return match ? match[1] : '';
                    }).filter(Boolean))];
                    if (postIds.length > 1) continue;
                    results.push({...photos[0], postId: postIds[0] || photos[0].photoId,
                        caption, caption_verified: true, caption_complete: true,
                        image_verified: true, createdTime, timeStr});
                }
                return results;
            }''')
            browser.close()

        posts = _posts_from_mobile_cards(cards, processed_ids, limit)
    except Exception as e:
        print(f" [PLAYWRIGHT FB ERROR] Error scraping {mobile_url}: {e}")

    return posts

def _extract_facebook_story_posts(scripts, processed_ids=None, limit=15, html='', source_url=''):
    """Read complete same-story caption/photo pairs from source hydration JSON."""
    processed_ids = processed_ids or []
    html = html or '\n'.join(scripts)
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

    # 2. Main pass: retain caption and photo owned by the same story object.
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
        Extract the exact message and a photo from one story object.
        Ambiguous wrappers and truncated messages are skipped.
        """
        if not isinstance(story_node, dict):
            return None
        if not _story_matches_source(story_node, source_url):
            return None

        # 1. Message text directly belonging to THIS story
        msg = _exact_story_caption(story_node)

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
                selected = _select_photo_from_attachment(a)
                if selected:
                    photo_id, img_url = selected
                    break

        # Construct crawler lookaside URI only as fallback for genuine numeric photo IDs
        if photo_id and not img_url:
            img_url = f"https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id={photo_id}"
        elif not img_url:
            # No confirmed photo on this story; video/link previews do not count.
            return None

        final_pid = pid_str or photo_id
        if not final_pid:
            return None

        created_time = post_meta.get(final_pid, 0)
        if not created_time and photo_id:
            created_time = post_meta.get(photo_id, 0)
        if not created_time:
            created_time = story_node.get("creation_time") or story_node.get("publish_time") or 0
        try:
            created_time = int(created_time)
        except (ValueError, TypeError):
            return None
        if created_time <= 0:
            # An unknown date must not become an invented fresh post.
            return None

        cap_fp = _caption_fingerprint(msg)

        return {
            "post_id": str(final_pid),
            "photo_id": str(photo_id or ""),
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

    posts = list(posts_dict.values())
    posts.sort(key=lambda p: p.get("created_time", 0), reverse=True)
    return posts[:limit]


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

    def public_route_fallback():
        # Facebook can serve a login shell for one route while its public
        # posts route still contains exact same-page caption/photo stories.
        # Do not transform direct story links into unrelated page feeds.
        from urllib.parse import urlsplit
        parsed=urlsplit(url)
        path=parsed.path.strip('/')
        if not path or '/' in path or path=='profile.php':
            return []
        for alternate in (f'https://www.facebook.com/{path}/posts/',
                          f'https://www.facebook.com/{path}?sk=posts'):
            try:
                response=requests.get(alternate,headers=FB_BOT_HEADERS,timeout=20)
                if response.status_code!=200 or 'facebook.com/login' in response.url.lower():
                    continue
                scripts=re.findall(r'<script\b(?=[^>]*\btype=["\']application/json["\'])[^>]*>(.*?)</script>',response.text,re.DOTALL)
                recovered=_extract_facebook_story_posts(scripts,processed_ids,limit,response.text,url)
                if recovered:
                    print(f' [FB INGEST] Recovered {len(recovered)} verified source pairs from the public posts route')
                    return recovered
            except requests.RequestException:
                continue
        return []

    try:
        res = requests.get(url, headers=FB_BOT_HEADERS, timeout=20)
    except Exception as e:
        print(f" [FB INGEST ERROR] Network request to {url} failed: {e}. Trying Playwright fallback...")
        return fetch_facebook_mobile_playwright(page_url_or_slug, processed_ids=processed_ids, limit=limit)

    if res.status_code != 200 or "facebook.com/login" in res.url.lower():
        print(f" [FB INGEST] URL {url} redirected to login or returned {res.status_code}. Engaging Playwright mobile bypass...")
        pw_posts = public_route_fallback() or fetch_facebook_mobile_playwright(page_url_or_slug, processed_ids=processed_ids, limit=limit)
        if pw_posts:
            return pw_posts
        return []

    html = res.text
    scripts = re.findall(r'<script\b(?=[^>]*\btype=["\']application/json["\'])[^>]*>(.*?)</script>', html, re.DOTALL)
    expected_source = res.url if _page_identity(res.url) else page_url_or_slug
    posts = _extract_facebook_story_posts(scripts, processed_ids, limit, html, expected_source)
    if not posts:
        print(f" [FB INGEST] Standard SSR yielded 0 posts for {url}. Engaging Playwright mobile bypass...")
        return public_route_fallback() or fetch_facebook_mobile_playwright(page_url_or_slug, processed_ids=processed_ids, limit=limit)
    return posts


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
                p["source_page_url"] = target
                all_posts.append(p)

    if all_posts:
        # Sort aggregated posts across all sources strictly by created_time descending
        all_posts.sort(key=lambda p: p.get("created_time", 0), reverse=True)
        print(f" [MULTI-SOURCE INGEST] Retrieved {len(all_posts)} post(s) from {len(targets)} source page(s)")
        return all_posts[:max(limit, 30)]

    return []
