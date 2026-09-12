import os
import sys
import json
import time
import shutil
import traceback
from datetime import datetime, timezone
from modules.ingestion import fetch_source_posts
from modules.image_cleaner import download_image, erase_text_and_watermarks, apply_cinematic_grade, validate_image_quality
from modules.llm_transformer import generate_social_payload
from modules.poster_engine import render_final_poster
from modules.publisher import publish_to_facebook
from modules.notifier import send_telegram_alert

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
    """Extracts core thematic keyword tokens for fuzzy cross-page story deduplication."""
    import re
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', (text or "").lower())
    tokens = [w for w in cleaned.split() if len(w) > 3 and w not in {'this', 'that', 'with', 'from', 'have', 'been', 'will', 'about', 'after', 'season', 'series', 'netflix'}][:8]
    return "_".join(sorted(tokens)) if tokens else ""

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"processed_ids": {}, "daily_stats": {}, "global_processed_ids": [], "global_story_fingerprints": []}
    return {"processed_ids": {}, "daily_stats": {}, "global_processed_ids": [], "global_story_fingerprints": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def run_pipeline(mode="run", target_channel="all"):
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
    # Guarantees that any news item published to ANY channel is NEVER posted to another channel
    all_published_ids = set(str(x) for x in state.get("global_processed_ids", []))
    for cid, id_list in processed_ids_map.items():
        all_published_ids.update(str(x) for x in id_list)
    global_story_fingerprints = set(state.get("global_story_fingerprints", []))

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
        cutoff_24h = now_current - 86400

        # 2. STRICT 24-HOUR FRESHNESS FILTER: Only consider genuine posts published within the last 24 hours
        recent_24h_posts = [
            p for p in candidate_posts
            if p.get("created_time", 0) >= cutoff_24h
        ]

        # 3. IDENTIFY UNPOSTED RECENT IMAGES (CROSS-PAGE UNIQUE)
        unposted_recent = []
        for p in recent_24h_posts:
            pid = str(p.get("post_id", ""))
            photo_id = str(p.get("photo_id", ""))
            cap_fp = str(p.get("caption_fingerprint", ""))
            story_fp = compute_story_fingerprint(p.get("caption", ""))

            # MUST NOT be posted to THIS channel OR ANY OTHER channel!
            is_duplicate = (
                pid in all_published_ids or
                photo_id in all_published_ids or
                cap_fp in all_published_ids or
                (story_fp and story_fp in global_story_fingerprints)
            )

            if not is_duplicate:
                unposted_recent.append(p)
            else:
                print(f"     [CROSS-PAGE DEDUP] Story '{p.get('caption', '')[:42]}...' already published to a channel. Skipping to keep content unique across all pages.")

        print(f" [24-HOUR AUDIT] Recent posts (< 24 hrs): {len(recent_24h_posts)} | Unposted & Unique across all channels: {len(unposted_recent)}")

        # RULE: "always use recent post only, dont use post older than 24 hrs"
        if not recent_24h_posts:
            print(f" [STRICT 24H GATE] No posts published within the last 24 hours found for '{channel_name}'. (Rule: Posts older than 24h are prohibited). Skipping channel.")
            continue

        # RULE: "if all of the recent posts (Not older than 24 hrs) is there dont post"
        if not unposted_recent:
            print(f" [UP TO DATE] All recent posts (< 24 hrs) are already published across managed channels. Nothing new to post for '{channel_name}'.")
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

        for post in candidates_to_try:
            post_id = post.get("post_id", "unknown")
            print(f"\n [+] 1-Hour Automatic Release: Evaluating Post {post_id}")
            print(f"     Destination: {channel_name} ({dest_id}) | Interval: {post_interval_hours}h | Mode: INSTANT LIVE POST ONLY")

            try:
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

                img_h, img_w = raw_img.shape[:2]
                print(f"           High-resolution source verified: {img_w}x{img_h}px ({quality_msg})")
                cleaned_img = erase_text_and_watermarks(raw_img)

                # 2. Cinematic Color Grading
                print("     [2/4] Applying OpenCV CIE-LAB CLAHE contrast grading...")
                graded_img = apply_cinematic_grade(cleaned_img)

                # 3. AI Caption & Dual-Tone Headline
                print("     [3/4] Generating dual-tone headline & policy-compliant caption...")
                ai_data = generate_social_payload(post.get("caption", ""))

                # 4. Composite 4:5 Poster
                rendered_file = os.path.join(OUTPUT_DIR, f"{channel_id}_{post_id}.jpg")
                print(f"     [4/4] Compositing 4:5 studio poster to {rendered_file}...")
                dest_name = ch.get("dest_page_name") or ch.get("channel_name") or channel_id
                render_final_poster(
                    base_img=graded_img,
                    overlay_lines=ai_data["overlay_lines"],
                    highlight_hex=highlight_hex,
                    dest_page_name=dest_name,
                    output_path=rendered_file,
                    post_id=post_id
                )
                print(f"           Poster created successfully: 1080x1350px")
                try:
                    from update_cache import update_posters_cache
                    update_posters_cache()
                except Exception:
                    pass

                # 5. INSTANT LIVE PUBLISHING ONLY (NO FB API SCHEDULING)
                print(f"     [PUBLISH] INSTANT LIVE POST to {dest_name} (Meta Graph API ID: {dest_id})")

                if mode in ["dry_run", "test"]:
                    print(f"     [DRY RUN] Simulated instant live publish to Facebook Page {dest_id}")
                    published_id = f"simulated_{post_id}"
                else:
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

                # Update channel state & global cross-page deduplication pool
                for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                    if id_val:
                        if id_val not in processed_ids:
                            processed_ids.append(id_val)
                        all_published_ids.add(id_val)

                post_story_fp = compute_story_fingerprint(post.get("caption", ""))
                if post_story_fp:
                    global_story_fingerprints.add(post_story_fp)

                channel_stat["count"] += 1
                channel_stat["timestamps"].append(datetime.now(timezone.utc).isoformat())
                channel_stat["last_published_time"] = now_current

                # Persist state with cross-page uniqueness guarantees
                processed_ids_map[channel_id] = processed_ids
                daily_stats[channel_id] = channel_stat
                state["processed_ids"] = processed_ids_map
                state["daily_stats"] = daily_stats
                state["global_processed_ids"] = list(all_published_ids)
                state["global_story_fingerprints"] = list(global_story_fingerprints)
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

        processed_ids_map[channel_id] = processed_ids
        daily_stats[channel_id] = channel_stat
        state["processed_ids"] = processed_ids_map
        state["daily_stats"] = daily_stats
        save_state(state)
    print("\n===================================================================")
    print("  Hourly Pipeline Execution Completed. State Saved.")
    print("===================================================================")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    target_channel = " ".join(sys.argv[2:]).strip() if len(sys.argv) > 2 else "all"

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