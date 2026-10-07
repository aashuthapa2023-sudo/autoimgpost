import os
import sys
import json
import time
import shutil
import traceback
import copy
from datetime import datetime, timezone
try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from modules.ingestion import fetch_source_posts
from modules.image_cleaner import (
    download_image,
    erase_text_and_watermarks,
    apply_cinematic_grade,
    validate_image_quality,
    compute_image_dhash
)
from modules.llm_transformer import generate_social_payload
from modules.poster_engine import render_final_poster
from modules.publisher import publish_to_facebook
from modules.publication_journal import record_publication, apply_publication_receipts
from modules.notifier import send_telegram_alert
try:
    from modules.web_scraper import fetch_web_news, get_channel_category
    WEB_SCRAPER_AVAILABLE = True
except ImportError:
    WEB_SCRAPER_AVAILABLE = False
    def fetch_web_news(*a, **kw): return []
    def get_channel_category(n): return "mixed"

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
OUTPUT_DIR = "output"
MAX_DAILY_LIMIT_PER_PAGE = 15
MIN_POST_GAP_SECONDS = 3600

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"{CONFIG_FILE} does not exist.")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"pipeline_active": True, "channels": data}
    return data

def candidate_queue_diagnostic(channel_name, scanned, cooldown, topic_rejected, stale, duplicates, eligible):
    """Explain an empty queue without implying rejected content was published."""
    counts = f"scanned={scanned}, retry_wait={cooldown}, topic_rejected={topic_rejected}, outside_72h={stale}, duplicates={duplicates}, eligible={eligible}"
    if eligible:
        return f" [READY QUEUE] {channel_name}: {eligible} candidate(s) awaiting image/headline checks. {counts}"
    if not scanned:
        return f" [NO SOURCE CANDIDATES] {channel_name}: No unprocessed complete caption/photo pairs were available from the configured sources. {counts}"
    if cooldown:
        return f" [QUALITY WAIT] {channel_name}: {cooldown} source post(s) are waiting after previous quality rejection; none is currently eligible. Review quality_report.json for reasons and retry times. {counts}"
    if topic_rejected:
        return f" [TOPIC WAIT] {channel_name}: Source posts were rejected for missing context or this page's topic. {counts}"
    if stale:
        return f" [STALE SOURCE] {channel_name}: Remaining source posts are outside the 72-hour window. {counts}"
    return f" [UP TO DATE] {channel_name}: {duplicates} recent source stories were already published. {counts}"


def compute_story_fingerprint(text: str) -> str:
    """Extracts core thematic keyword tokens for fuzzy story deduplication across both English and Nepali."""
    import re
    if not text:
        return ""
    words = re.findall(r'[^\s\.,!?;:\"\'।\(\)\[\]\{\}\-\—\–\/\\«»“”‘’#@]+', text.lower())
    stop_words = {
        'this', 'that', 'with', 'from', 'have', 'been', 'will', 'about', 'after', 
        'season', 'series', 'netflix', 'movie', 'first', 'look', 'what', 'know',
        'breaking', 'revealed', 'reportedly', 'officially', 'watch', 'upcoming',
        'could', 'would', 'should', 'their', 'there', 'they', 'them', 'these', 'those',
        'star', 'stars', 'show', 'shows', 'here', 'when', 'more', 'just', 'over', 'into',
        'than', 'also', 'some', 'were', 'very', 'even', 'most', 'such', 'only', 'same',
        'भनेका', 'भएको', 'गर्ने', 'हुने', 'गरेको', 'गरेका', 'रहेको', 'रहेका', 'छन्', 
        'थियो', 'थिए', 'पनि', 'लागि', 'भने', 'तथा', 'र', 'तर', 'भनेर', 'भनी',
        'आज', 'नयाँ', 'समाचार', 'अपडेट', 'नेपाल', 'गर्न', 'भई', 'हुन'
    }
    tokens = []
    for w in words:
        if (len(w) >= 3 or w.isdigit()) and w not in stop_words:
            if w not in tokens:
                tokens.append(w)
        if len(tokens) >= 18:
            break
    return "_".join(sorted(tokens)) if tokens else ""

def is_duplicate_dhash(cand_hash: str, hash_pool: set, max_hamming: int = 6) -> bool:
    """Checks if cand_hash is visually identical or near-duplicate to any hash in hash_pool."""
    if not cand_hash:
        return False
    try:
        cand_val = int(cand_hash, 16)
        for ex in hash_pool:
            ex_val = int(ex, 16)
            dist = bin(cand_val ^ ex_val).count("1")
            if dist <= max_hamming:
                return True
    except Exception:
        pass
    return False

def load_state():
    defaults = {
        "processed_ids": {},
        "daily_stats": {},
        "global_processed_ids": [],
        "global_story_fingerprints": [],
        "channel_story_fingerprints": {},
        "global_image_hashes": [],
        "global_processed_urls": []
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for k, v in defaults.items():
                    if k not in loaded:
                        loaded[k] = v
                return loaded
        except Exception:
            return defaults
    return defaults

def save_state(state):
    temp_path = STATE_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, STATE_FILE)

def run_pipeline(mode="run", target_channel="all"):
    if not mode or str(mode).strip().lower() in ["true", "none", ""]:
        mode = "run"
    if not target_channel or str(target_channel).strip().lower() in ["true", "none", ""]:
        target_channel = "all"

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    repo_slug = os.getenv("GITHUB_REPOSITORY", "aashuthapa2023-sudo/autoimgpost")
    print("===================================================================")
    print("  Facebook Multi-Page Hourly Automated Publisher (Zero-Cost Pipeline)")
    print(f"  Target Repository: https://github.com/{repo_slug}.git")
    print(f"  Execution Mode: {mode.upper()} | Filter: {target_channel}")
    print("===================================================================")

    config_data = load_config()
    pipeline_active = config_data.get("pipeline_active", True)
    channels = config_data.get("channels", [])

    if not pipeline_active and mode != "dry_run":
        print("[STATUS: PAUSED] Automation pipeline is currently PAUSED via control toggle.")
        print("To start auto-publishing, set pipeline_active to true in config.json or UI.")
        return

    state = load_state()
    state_before_recovery = copy.deepcopy(state)
    apply_publication_receipts(state)
    # Recover any confirmed publication whose later state save was interrupted.
    if state != state_before_recovery and mode not in ("dry_run", "test", "health_check"):
        save_state(state)
    processed_ids_map = state.get("processed_ids", {})
    daily_stats = state.get("daily_stats", {})

    # UNIVERSAL CROSS-PAGE DEDUPLICATION POOL:
    # Guarantees that any news item or image published to ANY channel is NEVER posted to another channel
    # UNIVERSAL & CHANNEL DEDUPLICATION POOLS:
    # Allows cross-channel syndication (e.g. Nepal Speaks & other outlets can both cover a story)
    # while strictly enforcing per-channel uniqueness (no repeats on the same channel).
    channel_image_hashes_map = state.get("channel_image_hashes", {})
    channel_story_fingerprints_map = state.get("channel_story_fingerprints", {})
    channel_recent_captions_map = state.get('channel_recent_source_captions', {})
    channel_clean_hashes_map = state.get('channel_clean_image_hashes', {})
    all_published_ids = set(str(x) for x in state.get("global_processed_ids", []))
    for cid, id_list in processed_ids_map.items():
        all_published_ids.update(str(x) for x in id_list)
    global_story_fingerprints = set(state.get("global_story_fingerprints", []))
    global_image_hashes = set(str(x) for x in state.get("global_image_hashes", []))
    global_processed_urls = set(str(x) for x in state.get("global_processed_urls", []))

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for ch in channels:
        channel_id = ch["channel_id"]
        channel_name = ch.get("channel_name", channel_id)
        from modules.quality_log import record_rejection, ready_candidates, profile_signature
        signature=profile_signature(ch)
        def reject(post_id,stage,reason):
            record_rejection(channel_id,post_id,stage,reason,policy_signature=signature)

        if target_channel != "all":
            t_clean = target_channel.strip().lower()
            cid_clean = str(channel_id).strip().lower()
            cname_clean = str(channel_name).strip().lower()
            if t_clean != cid_clean and t_clean != cname_clean and t_clean not in cid_clean:
                continue
        source_pages = ch.get("source_pages", [])
        if not source_pages:
            if ch.get("source_page_url"):
                source_pages = [ch["source_page_url"]]
            elif ch.get("source_page_id"):
                source_pages = [f"https://www.facebook.com/{ch['source_page_id']}"]

        source_id = ch.get("source_page_id", "")
        dest_id = ch.get("dest_page_id", "")
        token_env = ch.get("dest_access_token_env", "FB_TOKEN_DEFAULT")
        
        token = None
        if token_env and token_env.startswith("EAA"):
            token = token_env
        else:
            token = os.getenv(token_env)
            
        if not token and mode not in ('dry_run','health_check','test'):
            reject('', 'credential', 'This destination has no configured Facebook token')
            print(f" [CREDENTIAL REJECT] No token configured for {channel_id}; refusing another page's token")
            continue

        max_posts = int(ch.get("max_posts_per_run", 1))
        post_interval_hours = max(1.0, float(ch.get("post_interval_hours", ch.get("min_gap_hours", 1.0))))
        badge_label = ch.get("badge_label", ch.get("dest_page_name", "OFFICIAL UPDATE"))
        highlight_hex = ch.get("highlight_color", "random")

        print(f"\n-------------------------------------------------------------")
        print(f" Channel: {channel_name} ({channel_id})")
        print(f" Linked Source Pages: {len(source_pages)} sources -> Destination Page: {dest_id}")
        print(f" Configured Post Interval: {post_interval_hours} hour(s) | Max Posts per Run: {max_posts}")
        for sp in source_pages:
            print(f"   * Source: {sp}")

        # 1. STRICT CONSTRAINT: Max 15 images per day per page
        channel_stat = daily_stats.get(channel_id, {"date": today_str, "count": 0, "timestamps": [], "last_published_time": 0})
        if channel_stat.get("date") != today_str:
            channel_stat = {"date": today_str, "count": 0, "timestamps": [], "last_published_time": channel_stat.get("last_published_time", 0)}

        channel_max_daily = ch.get("max_daily_posts", config_data.get("max_images_per_day_per_page", MAX_DAILY_LIMIT_PER_PAGE))
        current_count = channel_stat.get("count", 0)
        remaining_today = max(0, channel_max_daily - current_count)
        print(f" [DAILY CAP CHECK] {current_count} / {channel_max_daily} posts published today ({remaining_today} remaining)")

        if current_count >= channel_max_daily:
            print(f" [HALT] Channel '{channel_name}' has reached its limit of {channel_max_daily} images today.")
            continue

        if not token:
            if mode == "dry_run" or mode == "test":
                print(f" [NOTICE] Channel '{channel_id}' has no {token_env} set; running in SIMULATED DRY RUN mode.")
                token = "SIMULATED_DEMO_TOKEN"
            else:
                print(f" [WARN] Skipping channel '{channel_id}': Missing environment token {token_env}")
                continue

        processed_ids = processed_ids_map.get(channel_id, [])
        channel_processed_ids = set(str(x) for x in processed_ids)
        channel_image_hashes = set(str(x) for x in channel_image_hashes_map.get(channel_id, []))
        channel_story_fps = set(channel_story_fingerprints_map.get(channel_id, []))
        recent_source_captions = channel_recent_captions_map.get(channel_id, [])
        clean_image_hashes = set(channel_clean_hashes_map.get(channel_id, []))

        try:
            # 1. Fetch recent candidates across all linked source pages
            candidate_posts = fetch_source_posts(
                page_id=source_id,
                access_token=token,
                processed_ids=list(channel_processed_ids),
                limit=60,
                source_urls=source_pages
            )
            print(f" [INGEST] Scanned {len(candidate_posts)} recent post(s) across {len(source_pages)} source page(s)")
            
            # Cache the latest source posts for UI feed
            if candidate_posts:
                try:
                    feed_payload = {
                        "success": True,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "channel_id": channel_id,
                        "page": source_pages[0] if source_pages else "",
                        "count": len(candidate_posts),
                        "posts": candidate_posts
                    }
                    with open("feed_cache.json", "w", encoding="utf-8") as ff:
                        json.dump(feed_payload, ff, indent=2)
                except Exception:
                    pass

        except Exception as err:
            tb_str = traceback.format_exc()
            print(f" [ERROR] Failed to fetch source posts: {err}")
            send_telegram_alert(
                phase="SOURCE_FEED_INGESTION",
                channel_name=channel_name,
                post_id="FEED_SCAN",
                error_message=str(err),
                traceback_str=tb_str
            )
            continue

        from modules.content_quality import channel_accepts_post
        scanned_count = len(candidate_posts)
        candidate_posts = ready_candidates(ch, candidate_posts, bypass=mode!='run')
        cooldown_count = scanned_count - len(candidate_posts)
        topic_rejected_count = 0
        topical_posts = []
        for candidate in candidate_posts:
            if channel_accepts_post(ch, candidate):
                topical_posts.append(candidate)
            else:
                topic_rejected_count += 1
                reject(candidate.get('post_id',''), 'topic_or_caption', 'Source caption is missing, context-free or outside this page topic')
        candidate_posts = topical_posts
        now_current = int(time.time())
        cutoff_24h  = now_current - 86400       # 24 hours ago
        cutoff_72h  = now_current - 259200      # 72 hours ago

        # 2. FRESHNESS TIERS — fresh first, older as fallback, web as last resort
        tier1_posts = [p for p in candidate_posts if p.get("created_time", 0) >= cutoff_24h or p.get("created_time", 0) == 0]   # <24h FB posts (or live feed posts without explicit timestamp)
        tier2_posts = [p for p in candidate_posts if cutoff_72h <= p.get("created_time", 0) < cutoff_24h]  # 24-72h FB posts

        # 3. IDENTIFY UNPOSTED UNIQUE POSTS in each tier for THIS channel
        # Strictly enforce per-channel story uniqueness (no repeats of the same story on this channel)
        def filter_unposted(posts):
            from modules.story_dedup import is_repeated_story
            result = []
            for p in posts:
                pid      = str(p.get("post_id", ""))
                photo_id = str(p.get("photo_id", ""))
                cap_fp   = str(p.get("caption_fingerprint", ""))
                story_fp = str(p.get("story_fingerprint") or compute_story_fingerprint(p.get("caption", "")))
                is_dup = (
                    pid in channel_processed_ids or
                    photo_id in channel_processed_ids or
                    cap_fp in channel_processed_ids or
                    (story_fp and story_fp in channel_story_fps) or
                    is_repeated_story(p.get('caption',''), recent_source_captions)
                )
                if not is_dup:
                    result.append(p)
                else:
                    print(f"     [CHANNEL DEDUP] Story '{p.get('caption', '')[:42]}...' already published by {channel_id}. Skipping duplicate.")
            return result

        unposted_t1 = filter_unposted(tier1_posts)
        unposted_t2 = filter_unposted(tier2_posts)

        print(f" [FRESHNESS AUDIT] FB <24h: {len(tier1_posts)} ({len(unposted_t1)} new)  |  FB 24-72h: {len(tier2_posts)} ({len(unposted_t2)} new)")

        # 4. WEB NEWS FALLBACK — fetch from internet when Facebook sources are dry
        web_posts = []
        is_nepali_ch = (ch.get("language") == "ne" or channel_id == "nepal_speaks")
        web_needed = (len(unposted_t1) == 0 and not is_nepali_ch and channel_id not in ('oceans_secret', 'Music Store') and ch.get('content_topic') != 'ocean' and ch.get('allow_web_fallback',False))  # Strictly disable English web fallback for Nepali channels!
        if web_needed and WEB_SCRAPER_AVAILABLE:
            category = get_channel_category(channel_name)
            print(f" [WEB FALLBACK] No fresh FB posts available. Fetching {category.upper()} news from internet...")
            raw_web_posts = fetch_web_news(
                category=category,
                processed_ids=list(channel_processed_ids),
                global_story_fps=list(channel_story_fps),
                limit=20,
                max_hours_old=72,
            )
            web_posts = filter_unposted(raw_web_posts)
            if web_posts:
                print(f" [WEB FALLBACK] Found {len(web_posts)} fresh unposted internet article(s) to fill the queue.")
            else:
                print(f" [WEB FALLBACK] No suitable unposted web articles found either.")

        # Build final priority-ordered candidate list: fresh FB first → older FB → web (strictly excluded for Nepali channels)
        unposted_recent = unposted_t1 + unposted_t2 + (web_posts if not is_nepali_ch else [])
        stale_count = len(candidate_posts) - len(tier1_posts) - len(tier2_posts)
        duplicate_count = len(tier1_posts) + len(tier2_posts) - len(unposted_t1) - len(unposted_t2)
        print(candidate_queue_diagnostic(channel_name, scanned_count, cooldown_count, topic_rejected_count,
                                         stale_count, duplicate_count, len(unposted_recent)))
        if not unposted_recent:
            continue

        # 4. STRICT 1-HOUR INTERVAL CADENCE:
        # "if there are still images not posted then post it in every 1 hr interval, make it work auto"
        last_pub_time = channel_stat.get("last_published_time", 0)
        # Guard against legacy scheduled future timestamps from old scheduling engine
        if last_pub_time > now_current:
            ts_list = channel_stat.get("timestamps", [])
            if ts_list:
                try:
                    last_dt = datetime.fromisoformat(ts_list[-1])
                    last_pub_time = int(last_dt.timestamp())
                except Exception:
                    last_pub_time = 0
            else:
                last_pub_time = 0
            channel_stat["last_published_time"] = last_pub_time

        gap_elapsed = now_current - last_pub_time
        effective_gap_seconds = int(float(post_interval_hours) * 3600)
        # 2-minute (120s) clock tolerance so scheduled cron checks trigger on-schedule without premature posting
        min_required_gap = max(0, effective_gap_seconds - 120)

        if last_pub_time > 0 and gap_elapsed < min_required_gap:
            remaining_mins = max(1, int((effective_gap_seconds - gap_elapsed) / 60))
            print(f" [CADENCE WAIT] Configured interval is {post_interval_hours}h. Only {gap_elapsed // 60}m elapsed since last post.")
            print(f"                Waiting {remaining_mins}m before next post. Automated pipeline will post on next cycle.")
            continue

        # 5. TAKE UP TO max_posts_per_run VALID UNPOSTED RECENT PHOTO POSTS FOR THIS CYCLE
        posted_successfully = False
        posts_published_this_run = 0
        candidates_to_try = unposted_recent
        if is_nepali_ch:
            candidates_to_try = [p for p in candidates_to_try if p.get("source_tag") != "Internet Web Scraper"]

        attempt_limit=max(max_posts,min(20,max(1,int(ch.get('max_candidates_per_run',6)))))
        processing_deadline=time.monotonic()+240
        for post in candidates_to_try[:attempt_limit]:
            if time.monotonic()>processing_deadline:
                print(' [PAGE BUDGET] Continuing the next page; remaining candidates can be checked in a later run')
                break
            post_id = post.get("post_id", "unknown")
            print(f"\n [+] 1-Hour Automatic Release: Evaluating Post {post_id}")
            print(f"     Destination: {channel_name} ({dest_id}) | Interval: {post_interval_hours}h | Mode: INSTANT LIVE POST ONLY")

            confirmed_meta_id = None
            try:
                # STRICT SOURCE LANGUAGE GATE FOR NEPALI CHANNELS:
                if is_nepali_ch:
                    from modules.llm_transformer import is_devanagari_text
                    post_cap = post.get("caption", "")
                    if not is_devanagari_text(post_cap):
                        reject(post_id, 'source_language', 'Source caption does not match the page language')
                        print(f"     [LANGUAGE REJECT] Channel '{channel_name}' requires 100% Nepali content. Skipping non-Nepali post {post_id}.")
                        continue

                # 1. Image Download & Smart Cleaner (strictly below center, faces & subjects 100% protected)
                image_url = post.get("image_url")
                if not image_url:
                    reject(post_id, 'source_image', 'Source post has no image URL')
                    print(f"     [SKIP] Post {post_id} has no image URL. Skipping.")
                    continue

                print("     [1/4] Downloading high-resolution source image...")
                raw_img = download_image(image_url)
                if raw_img is None:
                    reject(post_id, 'source_image', 'Image is unavailable or corrupt')
                    print(f"     [SKIP] Post {post_id} returned non-image or invalid media content. Will retry on a later scan; checking next candidate.")
                    continue

                # STRICT HD QUALITY GATE: Reject very low-resolution, blank, or excessively blurry images
                is_valid_quality, quality_msg = validate_image_quality(raw_img, min_dim=500, min_sharpness=80.0)
                if not is_valid_quality:
                    reject(post_id, 'source_quality', quality_msg)
                    print(f"     [QUALITY REJECT] Post {post_id} rejected: {quality_msg}.")
                    continue

                # STRICT CHANNEL VISUAL IMAGE DEDUPLICATION:
                # Verifies that this exact photo/image was NEVER published to THIS channel before
                img_dhash = compute_image_dhash(raw_img)
                if img_dhash and is_duplicate_dhash(img_dhash, channel_image_hashes):
                    reject(post_id, 'duplicate_photo', 'Source image was already published to this page')
                    print(f"     [CHANNEL IMAGE DEDUP] Image visually matches an image already published to {channel_id} (dHash: {img_dhash}). Skipping duplicate.")
                    continue

                img_h, img_w = raw_img.shape[:2]
                print(f"           High-resolution source verified: {img_w}x{img_h}px ({quality_msg})")

                # Detect original headline/text position ON THE UNTOUCHED RAW SOURCE IMAGE
                from modules.poster_engine import detect_image_text_position
                detected_text_pos = detect_image_text_position(raw_img)
                from modules.source_layout import get_source_layout
                source_layout = get_source_layout(ch, post, detected_text_pos)
                print(f"           [Text Placement Audit] Detected original source text position: {detected_text_pos.upper()}")

                from modules.image_cleaner import detect_source_text_boxes
                text_boxes = detect_source_text_boxes(raw_img)
                print(f"           [Source text cleanup] Checking {len(text_boxes)} regions for safe photo extraction")
                preserved_review = None
                try:
                    cleaned_img,crop_top,crop_bottom = erase_text_and_watermarks(raw_img, source_text_boxes=text_boxes,return_crop_bounds=True)
                except ValueError:
                    if not ch.get('preserve_readable_source_cards',False):
                        raise
                    from modules.source_card import inspect_readable_source_card
                    preserved_review = inspect_readable_source_card(raw_img,post.get('caption',''))
                    cleaned_img = raw_img
                    print(' [ORIGINAL CARD] Keeping its approved readable headline; no second headline will be added')

                # 2. Cinematic Color Grading
                print("     [2/4] Applying OpenCV CIE-LAB CLAHE contrast grading...")
                clean_valid, clean_reason = validate_image_quality(cleaned_img, min_dim=450, min_sharpness=35.0)
                if not clean_valid:
                    reject(post_id, 'photo_extraction', clean_reason)
                    print(f" [CLEANUP QUALITY REJECT] {post_id}: {clean_reason}")
                    continue
                clean_dhash = compute_image_dhash(cleaned_img)
                if clean_dhash and is_duplicate_dhash(clean_dhash, clean_image_hashes):
                    reject(post_id, 'duplicate_photo', 'Retained photograph was already published to this page')
                    continue
                graded_img = raw_img if preserved_review else apply_cinematic_grade(cleaned_img)

                # 3. AI Caption & Dual-Tone Headline
                ch_lang = ch.get("language", "en")
                is_nepali_ch = (ch_lang == "ne" or "nepal" in channel_id.lower() or "nepal" in channel_name.lower())
                if is_nepali_ch:
                    ch_lang = "ne"
                dest_name = ch.get("badge_label") or ch.get("dest_page_name") or ch.get("channel_name") or channel_id
                print(f"     [3/4] Generating dual-tone headline & policy-compliant caption (lang={ch_lang}, page={dest_name})...")
                try:
                    if preserved_review:
                        from modules.llm_transformer import generate_preserved_card_payload
                        ai_data = generate_preserved_card_payload(
                            post.get("caption",""), preserved_review["headline"],
                            language=ch_lang,channel_name=dest_name,channel_id=channel_id,
                            content_topic=ch.get('content_topic',''),editorial_style=ch.get('editorial_style',''))
                    else:
                        ai_data = generate_social_payload(
                            post.get("caption", ""),
                            language=ch_lang,
                            channel_name=dest_name,
                            channel_id=channel_id,
                            content_topic=ch.get('content_topic',''),
                            editorial_style=ch.get('editorial_style','')
                        )
                except ValueError as error:
                    if preserved_review or 'no complete readable headline' not in str(error):
                        raise
                    from modules.llm_transformer import clean_and_deduplicate_source_caption
                    from modules.source_headline import source_panel_payload
                    brief = clean_and_deduplicate_source_caption(post.get('caption',''),ch_lang,dest_name,channel_id,ch.get('content_topic',''))
                    ai_data = source_panel_payload(post.get('caption',''),brief,text_boxes,raw_img.shape,
                        (crop_top,crop_bottom),language=ch_lang,channel_name=dest_name,
                        channel_id=channel_id,content_topic=ch.get('content_topic',''))

                # STRICT OVERLAY LANGUAGE GATE FOR NEPALI CHANNELS:
                if is_nepali_ch:
                    from modules.llm_transformer import is_devanagari_text
                    overlay_all = "".join(t.get("text", "") for line in ai_data.get("overlay_lines", []) for t in line)
                    if not is_devanagari_text(overlay_all):
                        reject(post_id, 'headline_language', 'Generated headline does not match the page language')
                        print(f"     [LANGUAGE REJECT] Generated non-Devanagari overlay text for '{channel_name}'. Skipping post {post_id}.")
                        continue

                # 4. Composite 4:5 Poster
                rendered_file = os.path.join(OUTPUT_DIR, f"{channel_id}_{post_id}.jpg")
                print(f"     [4/4] Compositing 4:5 studio poster to {rendered_file}...")
                if preserved_review:
                    from modules.source_card import render_preserved_source_card
                    render_preserved_source_card(raw_img,preserved_review,ai_data['rewritten_caption'],dest_name,rendered_file,
                        highlight_hex=highlight_hex,**ch.get('poster_style',{}))
                else:
                    from modules.source_headline import render_with_source_fallback
                    ai_data = render_with_source_fallback(
                        ai_data,post.get('caption',''),text_boxes,raw_img.shape,(crop_top,crop_bottom),
                        language=ch_lang,channel_name=dest_name,channel_id=channel_id,
                        content_topic=ch.get('content_topic',''),render_fn=render_final_poster,
                        base_img=graded_img,
                        highlight_hex=highlight_hex,
                        dest_page_name=dest_name,
                        output_path=rendered_file,
                        post_id=post_id,
                        source_checked=True,
                        **{**ch.get('poster_style',{}), **source_layout}
                    )
                    if ai_data.get('headline_origin')=='removed_source_panel':
                        print(' [SOURCE HEADLINE] Reusing its complete validated title from the removed panel')
                print(f"           Poster created successfully: 1080x1350px")
                try:
                    from update_cache import update_posters_cache
                    update_posters_cache()
                except Exception:
                    pass

                # 5. Live Publish (INSTANT POST ONLY)
                if mode in ("dry_run", "health_check"):
                    print(f"     [DRY RUN] Skipping live post to Facebook ID {dest_id}. State preserved.")
                    posted_successfully = True
                    posts_published_this_run += 1
                    if posts_published_this_run >= max_posts or channel_stat["count"] >= channel_max_daily:
                        break
                    continue
                elif mode == "test":
                    print(f"     [TEST MODE] Live post skipped for {channel_id}. State preserved.")
                    posted_successfully = True
                    posts_published_this_run += 1
                    if posts_published_this_run >= max_posts or channel_stat["count"] >= channel_max_daily:
                        break
                    continue

                print(f"     [5/5] Publishing INSTANT photo post to Facebook (Page ID: {dest_id})...")
                try:
                    published_id = publish_to_facebook(
                        dest_page_id=dest_id,
                        access_token=token,
                        image_path=rendered_file,
                        caption=ai_data["rewritten_caption"],
                        scheduled_publish_time=None  # ALWAYS INSTANT POST ONLY!
                    )
                    confirmed_meta_id = published_id
                except Exception as pub_err:
                    print(f"     [PUBLISH REJECTED BY META] Graph API Error: {pub_err}")
                    if "deleted" in str(pub_err).lower() or "190" in str(pub_err):
                        reject('', 'credential', 'Facebook rejected this page connection; reconnect with a fresh page token')
                        print(f"     [ACTION REQUIRED] The Meta Facebook App for '{dest_name}' (ID: {dest_id}) was deleted or token expired.")
                        print(f"     Please generate a fresh Page Access Token on Meta Developers and paste it into Web UI Settings.")
                    raise pub_err

                published_at = datetime.now(timezone.utc)
                post_story_fp = str(post.get("story_fingerprint") or compute_story_fingerprint(post.get("caption", "")))
                # Keep the confirmed Meta receipt before updating the broader ledger.
                # A failed later save or Git push must never make this source eligible again.
                record_publication(
                    channel_id, dict(post, post_id=str(post_id)), published_id,
                    published_at=published_at.isoformat(),
                    image_hash=img_dhash, clean_image_hash=clean_dhash,
                    story_fingerprint=post_story_fp,
                )
                print(f"     [SUCCESS] Live Instant Post Published! Meta ID: {published_id}")

                # Update channel state ONLY after actual live publish succeeds
                for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                    if id_val:
                        if id_val not in processed_ids:
                            processed_ids.append(id_val)
                            channel_processed_ids.add(id_val)
                        all_published_ids.add(id_val)

                if img_dhash:
                    channel_image_hashes.add(img_dhash)
                    global_image_hashes.add(img_dhash)
                if clean_dhash:
                    clean_image_hashes.add(clean_dhash)

                if image_url:
                    global_processed_urls.add(image_url)

                if post_story_fp:
                    global_story_fingerprints.add(post_story_fp)
                    channel_story_fps.add(post_story_fp)

                channel_stat["count"] += 1
                channel_stat["timestamps"].append(published_at.isoformat())
                channel_stat["last_published_time"] = int(published_at.timestamp())

                # Persist state with per-channel tracking & cross-channel syndication support
                channel_image_hashes_map[channel_id] = list(channel_image_hashes)
                channel_story_fingerprints_map[channel_id] = list(channel_story_fps)
                recent_source_captions.append(str(post.get('caption',''))[:4000])
                channel_recent_captions_map[channel_id] = recent_source_captions[-80:]
                channel_clean_hashes_map[channel_id] = list(clean_image_hashes)[-300:]
                state['channel_recent_source_captions'] = channel_recent_captions_map
                state['channel_clean_image_hashes'] = channel_clean_hashes_map
                state["channel_image_hashes"] = channel_image_hashes_map
                state["channel_story_fingerprints"] = channel_story_fingerprints_map
                processed_ids_map[channel_id] = processed_ids
                daily_stats[channel_id] = channel_stat
                state["processed_ids"] = processed_ids_map
                state["daily_stats"] = daily_stats
                state["global_processed_ids"] = list(all_published_ids)
                state["global_story_fingerprints"] = list(global_story_fingerprints)
                state["global_image_hashes"] = list(global_image_hashes)
                state["global_processed_urls"] = list(global_processed_urls)
                save_state(state)

                posted_successfully = True
                posts_published_this_run += 1
                if posts_published_this_run >= max_posts or channel_stat["count"] >= channel_max_daily:
                    print(f"     [CYCLE TARGET REACHED] Published {posts_published_this_run} / {max_posts} configured post(s) for this run (Daily count: {channel_stat['count']}/{channel_max_daily}).")
                    break
                print(f"     [MULTI-POST BATCH] Successfully published {posts_published_this_run}/{max_posts}. Continuing to next candidate in 5s...")
                time.sleep(5)

            except Exception as err:
                if confirmed_meta_id:
                    print(f" [CONFIRMED POST RECOVERY REQUIRED] Channel: {channel_id}; source: {post_id}; Meta ID: {confirmed_meta_id}")
                    raise RuntimeError("Confirmed publication receipt/state could not be saved; stop and recover before another run") from err
                if isinstance(err, ValueError):
                    reject(post_id, 'content_or_layout', str(err))
                    print(f"     [QUALITY SKIP] Post {post_id}: {err}")
                    continue
                tb_str = traceback.format_exc()
                print(f"     [ERROR] Post {post_id} failed: {err}")
                send_telegram_alert(
                    phase="POST_PROCESSING_OR_PUBLISH",
                    channel_name=channel_name,
                    post_id=post_id,
                    error_message=str(err),
                    traceback_str=tb_str
                )
                if "validating access token" in str(err).lower() or "session has been invalidated" in str(err).lower():
                    print(f"     [TOKEN EXPIRED] Access token for '{channel_name}' is invalid. Skipping channel.")
                    break

        if not posted_successfully:
            print(f" [PAGE BLOCKED] {channel_name}: No candidate completed image, caption and publication checks this cycle. Review the quality skips and publishing errors above; remaining candidates stay pending.")
        processed_ids_map[channel_id] = processed_ids
        daily_stats[channel_id] = channel_stat
        state["processed_ids"] = processed_ids_map
        state["daily_stats"] = daily_stats
        if mode not in ("dry_run", "test", "health_check"):
            save_state(state)
    print("\n===================================================================")
    print("  Hourly Pipeline Execution Completed. Review page results above.")
    print("===================================================================")

def main():
    raw_mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    raw_target = " ".join(sys.argv[2:]).strip() if len(sys.argv) > 2 else "all"

    mode = "run" if raw_mode.strip().lower() in ["true", "none", ""] else raw_mode.strip()
    target_channel = "all" if raw_target.strip().lower() in ["true", "none", ""] else raw_target.strip()

    if mode in ["daemon", "auto", "loop"]:
        print("===================================================================")
        print("  Facebook Multi-Page Continuous 24/7 Background Daemon Started")
        print(f"  Target: {target_channel} | Interval: Checking cadence every 5 minutes")
        print("===================================================================")
        while True:
            try:
                run_pipeline(mode="run", target_channel=target_channel)
            except Exception as e:
                print(f"[DAEMON CYCLE ERROR] {e}")
                traceback.print_exc()
            print("\n[DAEMON SLEEP] Waiting 5 minutes before next automated cadence check...\n")
            time.sleep(300)
    else:
        run_pipeline(mode=mode, target_channel=target_channel)

if __name__ == "__main__":
    main()
