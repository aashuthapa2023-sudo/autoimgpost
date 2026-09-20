import os
import sys
import json
import time
import shutil
import traceback
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
        if len(w) >= 3 and w not in stop_words and not w.isdigit():
            if w not in tokens:
                tokens.append(w)
        if len(tokens) >= 8:
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
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

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
    processed_ids_map = state.get("processed_ids", {})
    daily_stats = state.get("daily_stats", {})

    # UNIVERSAL CROSS-PAGE DEDUPLICATION POOL:
    # Guarantees that any news item or image published to ANY channel is NEVER posted to another channel
    # UNIVERSAL & CHANNEL DEDUPLICATION POOLS:
    # Allows cross-channel syndication (e.g. Nepal Speaks & other outlets can both cover a story)
    # while strictly enforcing per-channel uniqueness (no repeats on the same channel).
    channel_image_hashes_map = state.get("channel_image_hashes", {})
    channel_story_fingerprints_map = state.get("channel_story_fingerprints", {})
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
            
        if not token:
            for fallback_key in ["FB_TOKEN_MUSIC_STORE", "MUSIC_STORE_TOKEN", "FB_TOKEN_DAILY_NETFLIX", "DAILY_NETFLIX_TOKEN", "FB_TOKEN_CINEMA", "FB_TOKEN_DEFAULT"]:
                cand = os.getenv(fallback_key)
                if cand:
                    token = cand
                    break

        max_posts = ch.get("max_posts_per_run", 1)
        post_interval_hours = float(ch.get("post_interval_hours", ch.get("min_gap_hours", 1.0)))
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

        current_count = channel_stat.get("count", 0)
        remaining_today = MAX_DAILY_LIMIT_PER_PAGE - current_count
        print(f" [DAILY CAP CHECK] {current_count} / {MAX_DAILY_LIMIT_PER_PAGE} posts published today ({remaining_today} remaining)")

        if current_count >= MAX_DAILY_LIMIT_PER_PAGE:
            print(f" [HALT] Channel '{channel_name}' has reached its strict limit of {MAX_DAILY_LIMIT_PER_PAGE} images today.")
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

        try:
            # 1. Fetch recent candidates across all linked source pages
            candidate_posts = fetch_source_posts(
                page_id=source_id,
                access_token=token,
                processed_ids=[],  # scan raw to evaluate 24-hr status
                limit=15,
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

        now_current = int(time.time())
        cutoff_24h  = now_current - 86400       # 24 hours ago
        cutoff_72h  = now_current - 259200      # 72 hours ago

        # 2. FRESHNESS TIERS — fresh first, older as fallback, web as last resort
        tier1_posts = [p for p in candidate_posts if p.get("created_time", 0) >= cutoff_24h]   # <24h FB posts
        tier2_posts = [p for p in candidate_posts if cutoff_72h <= p.get("created_time", 0) < cutoff_24h]  # 24-72h FB posts

        # 3. IDENTIFY UNPOSTED UNIQUE POSTS in each tier for THIS channel
        # Strictly enforce per-channel story uniqueness (no repeats of the same story on this channel)
        def filter_unposted(posts):
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
                    (story_fp and story_fp in channel_story_fps)
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
        web_needed = (len(unposted_t1) == 0 and not is_nepali_ch)  # Strictly disable English web fallback for Nepali channels!
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
        unposted_recent = unposted_t1 or unposted_t2 or (web_posts if not is_nepali_ch else [])

        if not unposted_t1 and not unposted_t2 and (not web_posts or is_nepali_ch):
            print(f" [UP TO DATE] All content already published or no new content available for '{channel_name}'.")
            continue

        if not unposted_recent:
            print(f" [UP TO DATE] Nothing new to post for '{channel_name}'.")
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
        # 5-minute (300s) grace tolerance so 15m cron checks trigger on-schedule without skipping a whole cycle
        min_required_gap = max(0, effective_gap_seconds - 300)

        if last_pub_time > 0 and gap_elapsed < min_required_gap:
            remaining_mins = max(1, int((effective_gap_seconds - gap_elapsed) / 60))
            print(f" [CADENCE WAIT] Configured interval is {post_interval_hours}h. Only {gap_elapsed // 60}m elapsed since last post.")
            print(f"                Waiting {remaining_mins}m before next post. Automated pipeline will post on next cycle.")
            continue

        # 5. TAKE EXACTLY 1 VALID UNPOSTED RECENT PHOTO POST FOR THIS 1-HOUR CYCLE (chronological order)
        posted_successfully = False
        candidates_to_try = list(reversed(unposted_recent))
        if is_nepali_ch:
            candidates_to_try = [p for p in candidates_to_try if p.get("source_tag") != "Internet Web Scraper"]

        for post in candidates_to_try:
            post_id = post.get("post_id", "unknown")
            print(f"\n [+] 1-Hour Automatic Release: Evaluating Post {post_id}")
            print(f"     Destination: {channel_name} ({dest_id}) | Interval: {post_interval_hours}h | Mode: INSTANT LIVE POST ONLY")

            try:
                # STRICT SOURCE LANGUAGE GATE FOR NEPALI CHANNELS:
                if is_nepali_ch:
                    from modules.llm_transformer import is_devanagari_text
                    post_cap = post.get("caption", "")
                    if not is_devanagari_text(post_cap):
                        print(f"     [LANGUAGE REJECT] Channel '{channel_name}' requires 100% Nepali content. Skipping non-Nepali post {post_id}.")
                        for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                            if id_val and id_val not in processed_ids:
                                processed_ids.append(id_val)
                                all_published_ids.add(id_val)
                        continue

                # 1. Image Download & Smart Cleaner (strictly below center, faces & subjects 100% protected)
                image_url = post.get("image_url")
                if not image_url:
                    print(f"     [SKIP] Post {post_id} has no image URL. Skipping.")
                    for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                        if id_val and id_val not in processed_ids:
                            processed_ids.append(id_val)
                            all_published_ids.add(id_val)
                    continue

                print("     [1/4] Downloading high-resolution source image...")
                raw_img = download_image(image_url)
                if raw_img is None:
                    print(f"     [SKIP] Post {post_id} returned non-image or invalid media content. Marking processed and checking next candidate.")
                    for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                        if id_val and id_val not in processed_ids:
                            processed_ids.append(id_val)
                            all_published_ids.add(id_val)
                    continue

                # STRICT HD QUALITY GATE: Reject any low-resolution, blurry, or pixelated images
                is_valid_quality, quality_msg = validate_image_quality(raw_img, min_dim=720, min_sharpness=160.0)
                if not is_valid_quality:
                    print(f"     [QUALITY REJECT] Post {post_id} rejected: {quality_msg}. Skipping to guarantee zero blur and zero pixelation.")
                    for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                        if id_val and id_val not in processed_ids:
                            processed_ids.append(id_val)
                            all_published_ids.add(id_val)
                    continue

                # STRICT CHANNEL VISUAL IMAGE DEDUPLICATION:
                # Verifies that this exact photo/image was NEVER published to THIS channel before
                img_dhash = compute_image_dhash(raw_img)
                if img_dhash and is_duplicate_dhash(img_dhash, channel_image_hashes):
                    print(f"     [CHANNEL IMAGE DEDUP] Image visually matches an image already published to {channel_id} (dHash: {img_dhash}). Skipping duplicate.")
                    for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                        if id_val and id_val not in processed_ids:
                            processed_ids.append(id_val)
                            channel_processed_ids.add(id_val)
                    continue

                img_h, img_w = raw_img.shape[:2]
                print(f"           High-resolution source verified: {img_w}x{img_h}px ({quality_msg})")

                # Detect original headline/text position ON THE UNTOUCHED RAW SOURCE IMAGE
                from modules.poster_engine import detect_image_text_position
                detected_text_pos = detect_image_text_position(raw_img)
                print(f"           [Text Placement Audit] Detected original source text position: {detected_text_pos.upper()}")

                cleaned_img = erase_text_and_watermarks(raw_img)

                # 2. Cinematic Color Grading
                print("     [2/4] Applying OpenCV CIE-LAB CLAHE contrast grading...")
                graded_img = apply_cinematic_grade(cleaned_img)

                # 3. AI Caption & Dual-Tone Headline
                ch_lang = ch.get("language", "en")
                is_nepali_ch = (ch_lang == "ne" or "nepal" in channel_id.lower() or "nepal" in channel_name.lower())
                if is_nepali_ch:
                    ch_lang = "ne"
                dest_name = ch.get("badge_label") or ch.get("dest_page_name") or ch.get("channel_name") or channel_id
                print(f"     [3/4] Generating dual-tone headline & policy-compliant caption (lang={ch_lang}, page={dest_name})...")
                ai_data = generate_social_payload(
                    post.get("caption", ""),
                    language=ch_lang,
                    channel_name=dest_name,
                    channel_id=channel_id
                )

                # STRICT OVERLAY LANGUAGE GATE FOR NEPALI CHANNELS:
                if is_nepali_ch:
                    from modules.llm_transformer import is_devanagari_text
                    overlay_all = "".join(t.get("text", "") for line in ai_data.get("overlay_lines", []) for t in line)
                    if not is_devanagari_text(overlay_all):
                        print(f"     [LANGUAGE REJECT] Generated non-Devanagari overlay text for '{channel_name}'. Skipping post {post_id}.")
                        for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                            if id_val and id_val not in processed_ids:
                                processed_ids.append(id_val)
                                channel_processed_ids.add(id_val)
                                all_published_ids.add(id_val)
                        continue

                # 4. Composite 4:5 Poster
                rendered_file = os.path.join(OUTPUT_DIR, f"{channel_id}_{post_id}.jpg")
                print(f"     [4/4] Compositing 4:5 studio poster to {rendered_file}...")
                render_final_poster(
                    base_img=graded_img,
                    overlay_lines=ai_data["overlay_lines"],
                    highlight_hex=highlight_hex,
                    dest_page_name=dest_name,
                    output_path=rendered_file,
                    post_id=post_id,
                    text_position=detected_text_pos
                )
                print(f"           Poster created successfully: 1080x1350px")
                try:
                    from update_cache import update_posters_cache
                    update_posters_cache()
                except Exception:
                    pass

                # 5. Live Publish (INSTANT POST ONLY)
                if mode == "dry_run":
                    print(f"     [DRY RUN] Skipping live post to Facebook ID {dest_id}. State preserved.")
                    posted_successfully = True
                    break
                elif mode == "test":
                    print(f"     [TEST MODE] Live post skipped for {channel_id}. State preserved.")
                    posted_successfully = True
                    break

                print(f"     [5/5] Publishing INSTANT photo post to Facebook (Page ID: {dest_id})...")
                try:
                    published_id = publish_to_facebook(
                        dest_page_id=dest_id,
                        access_token=token,
                        image_path=rendered_file,
                        caption=ai_data["rewritten_caption"],
                        scheduled_publish_time=None  # ALWAYS INSTANT POST ONLY!
                    )
                    print(f"     [SUCCESS] Live Instant Post Published! Meta ID: {published_id}")
                except Exception as pub_err:
                    print(f"     [PUBLISH REJECTED BY META] Graph API Error: {pub_err}")
                    if "deleted" in str(pub_err).lower() or "190" in str(pub_err):
                        print(f"     [ACTION REQUIRED] The Meta Facebook App for '{dest_name}' (ID: {dest_id}) was deleted or token expired.")
                        print(f"     Please generate a fresh Page Access Token on Meta Developers and paste it into Web UI Settings.")
                    raise pub_err

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

                if image_url:
                    global_processed_urls.add(image_url)

                post_story_fp = str(post.get("story_fingerprint") or compute_story_fingerprint(post.get("caption", "")))
                if post_story_fp:
                    global_story_fingerprints.add(post_story_fp)
                    channel_story_fps.add(post_story_fp)

                channel_stat["count"] += 1
                channel_stat["timestamps"].append(datetime.now(timezone.utc).isoformat())
                channel_stat["last_published_time"] = now_current

                # Persist state with per-channel tracking & cross-channel syndication support
                channel_image_hashes_map[channel_id] = list(channel_image_hashes)
                channel_story_fingerprints_map[channel_id] = list(channel_story_fps)
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
                break  # Exactly 1 post per hour cycle completed!

            except Exception as err:
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

        processed_ids_map[channel_id] = processed_ids
        daily_stats[channel_id] = channel_stat
        state["processed_ids"] = processed_ids_map
        state["daily_stats"] = daily_stats
        save_state(state)
    print("\n===================================================================")
    print("  Hourly Pipeline Execution Completed. State Saved.")
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