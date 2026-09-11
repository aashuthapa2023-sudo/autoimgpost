import os
import sys
import json
import time
import shutil
import traceback
from datetime import datetime, timezone
from modules.ingestion import fetch_source_posts
from modules.image_cleaner import download_image, erase_text_and_watermarks, apply_cinematic_grade
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

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"processed_ids": {}, "daily_stats": {}}
    return {"processed_ids": {}, "daily_stats": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    target_channel = sys.argv[2] if len(sys.argv) > 2 else "all"

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

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for ch in channels:
        channel_id = ch["channel_id"]
        if target_channel != "all" and target_channel != channel_id:
            continue

        channel_name = ch.get("channel_name", channel_id)
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
            for fallback_key in ["FB_TOKEN_DAILY_NETFLIX", "DAILY_NETFLIX_TOKEN", "FB_TOKEN_CINEMA", "FB_TOKEN_DEFAULT"]:
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
            allowed_to_fetch = min(max_posts, remaining_today)
            new_posts = fetch_source_posts(
                page_id=source_id,
                access_token=token,
                processed_ids=processed_ids,
                limit=allowed_to_fetch,
                source_urls=source_pages
            )
            print(f" [INGEST] Found {len(new_posts)} new unprocessed post(s) from multi-source Facebook pages")
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

        accumulated_gap_seconds = 0
        last_pub_time = channel_stat.get("last_published_time", 0)

        for post in new_posts:
            if channel_stat["count"] >= MAX_DAILY_LIMIT_PER_PAGE:
                print(f" [DAILY CAP REACHED] Hit {MAX_DAILY_LIMIT_PER_PAGE} posts limit for {channel_id}. Stopping batch.")
                break

            post_id = post["post_id"]
            source_gap_hours = post.get("source_gap_hours", 2.0)

            # 2. STRICT CONSTRAINT: Channel-defined post interval hours
            effective_gap_hours = max(0.1, float(post_interval_hours))
            effective_gap_seconds = int(effective_gap_hours * 3600)

            print(f"\n [+] Processing Post: {post_id}")
            print(f"     Enforced Schedule Gap: {effective_gap_hours}h (Page Interval Configured)")

            try:
                # 1. Image Download & Smart Cleaner
                print("     [1/5] Downloading image from Facebook crawler CDN...")
                raw_img = download_image(post["image_url"])
                print(f"           Source image downloaded: {raw_img.shape[1]}x{raw_img.shape[0]}px")
                cleaned_img = erase_text_and_watermarks(raw_img)

                # 2. Cinematic Color Grading
                print("     [2/5] Applying OpenCV CIE-LAB CLAHE contrast grading...")
                graded_img = apply_cinematic_grade(cleaned_img)

                # 3. AI Caption & Dual-Tone Headline
                print("     [3/5] Generating dual-tone headline & policy-compliant caption...")
                ai_data = generate_social_payload(post["caption"])

                # 4. Composite 4:5 Poster
                rendered_file = os.path.join(OUTPUT_DIR, f"{channel_id}_{post_id}.jpg")
                print(f"     [4/5] Compositing 4:5 studio poster to {rendered_file}...")
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

                # 5. Scheduling / Publishing
                now_current = int(time.time())
                candidate_time_now = now_current + accumulated_gap_seconds + (effective_gap_seconds if accumulated_gap_seconds > 0 else 0)
                min_time_from_last = (last_pub_time + effective_gap_seconds) if last_pub_time > 0 else candidate_time_now

                target_publish_ts = max(candidate_time_now, min_time_from_last)
                sched_dt = datetime.fromtimestamp(target_publish_ts, tz=timezone.utc)
                sched_str = sched_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

                # Meta Graph API strictly requires scheduled_publish_time to be >= 10 minutes (600s) in future.
                # If target is now or within 10 minutes, pass None to publish immediately!
                api_sched_ts = target_publish_ts if (target_publish_ts > now_current + 600) else None

                if api_sched_ts:
                    print(f"     [5/5] Target Scheduled Time: {sched_str} (Meta Future Queue)")
                else:
                    print(f"     [5/5] Target Publish Time: IMMEDIATE LIVE PUBLISH to {dest_name}")

                if mode in ["dry_run", "test"]:
                    print(f"     [DRY RUN] Would publish to Facebook Page {dest_id} (Target: {sched_str})")
                    published_id = f"simulated_{post_id}"
                else:
                    published_id = publish_to_facebook(
                        dest_page_id=dest_id,
                        access_token=token,
                        image_path=rendered_file,
                        caption=ai_data["rewritten_caption"],
                        scheduled_publish_time=api_sched_ts
                    )
                    print(f"     [SUCCESS] Published to Meta Graph API ID: {published_id}")

                # Update state & counters with multi-key deduplication
                for id_val in [str(post_id), str(post.get("photo_id", "")), str(post.get("caption_fingerprint", ""))]:
                    if id_val and id_val not in processed_ids:
                        processed_ids.append(id_val)

                channel_stat["count"] += 1
                channel_stat["timestamps"].append(datetime.now(timezone.utc).isoformat())
                channel_stat["last_published_time"] = target_publish_ts
                last_pub_time = target_publish_ts
                accumulated_gap_seconds += effective_gap_seconds

                # Save state after each successful post to guarantee deduplication persistence
                processed_ids_map[channel_id] = processed_ids
                daily_stats[channel_id] = channel_stat
                state["processed_ids"] = processed_ids_map
                state["daily_stats"] = daily_stats
                save_state(state)

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

if __name__ == "__main__":
    main()
