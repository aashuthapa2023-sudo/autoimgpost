import os
import sys
import json
import time
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
MAX_DAILY_LIMIT_PER_PAGE = 15  # STRICT RULE: Must not exceed 15 images per day per page
MIN_POST_GAP_SECONDS = 3600    # STRICT RULE: At least 1 hour (3600s) gap per post

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"{CONFIG_FILE} does not exist.")
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"pipeline_active": True, "channels": data}
    return data

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"processed_ids": {}, "daily_stats": {}}
    return {"processed_ids": {}, "daily_stats": {}}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    target_channel = sys.argv[2] if len(sys.argv) > 2 else "all"

    print("===================================================================")
    print("  Facebook Multi-Page Hourly Automated Publisher (Zero-Cost Pipeline)")
    print(f"  Target Repository: https://github.com/{repoOwner}/{repoName}.git")
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
    now_ts = int(time.time())

    for ch in channels:
        channel_id = ch["channel_id"]
        if target_channel != "all" and target_channel != channel_id:
            continue

        channel_name = ch.get("channel_name", channel_id)
        source_url = ch.get("source_page_url", "")
        source_id = ch["source_page_id"]
        dest_id = ch["dest_page_id"]
        token_env = ch["dest_access_token_env"]
        token = os.getenv(token_env)
        max_posts = ch.get("max_posts_per_run", 2)
        cadence_mirror = ch.get("cadence_mirror_enabled", True)

        print(f"\n-------------------------------------------------------------")
        print(f" Channel: {channel_name} ({channel_id})")
        print(f" Source URL: {source_url or source_id} -> Destination Page: {dest_id}")

        # -----------------------------------------------------------------
        # STRICT CONSTRAINT 1: Max 15 images per day per page
        # -----------------------------------------------------------------
        channel_stat = daily_stats.get(channel_id, {"date": today_str, "count": 0, "timestamps": [], "last_published_time": 0})
        if channel_stat.get("date") != today_str:
            channel_stat = {"date": today_str, "count": 0, "timestamps": [], "last_published_time": channel_stat.get("last_published_time", 0)}

        current_count = channel_stat.get("count", 0)
        remaining_today = MAX_DAILY_LIMIT_PER_PAGE - current_count
        print(f" [DAILY CAP CHECK] {current_count} / {MAX_DAILY_LIMIT_PER_PAGE} posts published today ({remaining_today} remaining)")

        if current_count >= MAX_DAILY_LIMIT_PER_PAGE:
            print(f" [HALT] Channel '{channel_name}' has reached its strict limit of {MAX_DAILY_LIMIT_PER_PAGE} images today.")
            print(" Skipping until the next 24-hour UTC reset to protect page distribution and policy rating.")
            continue

        if not token:
            print(f" [WARN] Skipping channel '{channel_id}': Missing environment token {token_env}")
            continue

        processed_ids = processed_ids_map.get(channel_id, [])

        try:
            allowed_to_fetch = min(max_posts, remaining_today)
            new_posts = fetch_source_posts(source_id, token, processed_ids, limit=allowed_to_fetch, source_url=source_url)
            print(f" [INGEST] Found {len(new_posts)} new unprocessed post(s)")
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
            # Double check daily cap before each image
            if channel_stat["count"] >= MAX_DAILY_LIMIT_PER_PAGE:
                print(f" [DAILY CAP REACHED] Hit {MAX_DAILY_LIMIT_PER_PAGE} posts limit for {channel_id}. Stopping batch.")
                break

            post_id = post["post_id"]
            source_gap_hours = post.get("source_gap_hours", 2.0)

            # -------------------------------------------------------------
            # STRICT CONSTRAINT 2: At least 1 hour gap per post in a page
            # -------------------------------------------------------------
            effective_gap_hours = max(1.0, float(source_gap_hours))
            effective_gap_seconds = int(effective_gap_hours * 3600)

            print(f"\n [+] Post: {post_id}")
            print(f"     Source hour gap: {source_gap_hours}h | Enforced gap: {effective_gap_hours}h (>= 1 hour rule satisfied)")

            try:
                # 1. Image Text & Watermark Erasure (Local EasyOCR + OpenCV Telea)
                print("     [1/5] Erasing source watermarks & subtitles with CPU EasyOCR + Inpainting...")
                raw_img = download_image(post["image_url"])
                cleaned_img = erase_text_and_watermarks(raw_img)

                # 2. Cinematic Color Grading (CLAHE & Tone Enhancement)
                print("     [2/5] Applying OpenCV CLAHE LAB contrast grading...")
                graded_img = apply_cinematic_grade(cleaned_img)

                # 3. AI Caption & Headline (Multi-Provider Waterfall: Groq -> Gemini -> OpenRouter -> Local)
                print("     [3/5] Executing Zero-Cost LLM Failover Waterfall...")
                ai_data = generate_social_payload(post["caption"])

                # 4. Composite 4:5 Poster with Gradient & Bold Typography
                rendered_file = f"temp_{channel_id}_{post_id}.jpg"
                print(f"     [4/5] Compositing 4:5 poster typography to {rendered_file}...")
                render_final_poster(
                    base_img=graded_img,
                    overlay_lines=ai_data["overlay_lines"],
                    highlight_hex=ch.get("highlight_color", "#FFC83B"),
                    badge_path=ch.get("logo_badge"),
                    output_path=rendered_file
                )

                # 5. Scheduling / Publishing with guaranteed minimum 1 hour spacing
                now_current = int(time.time())
                candidate_time_now = now_current + accumulated_gap_seconds + (effective_gap_seconds if accumulated_gap_seconds > 0 else 0)
                min_time_from_last = (last_pub_time + MIN_POST_GAP_SECONDS) if last_pub_time > 0 else candidate_time_now

                target_publish_ts = max(candidate_time_now, min_time_from_last)
                sched_dt = datetime.fromtimestamp(target_publish_ts, tz=timezone.utc)
                sched_str = sched_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

                print(f"     [5/5] Enforced Schedule: {sched_str} (>= 1 hour gap guaranteed)")

                if mode == "dry_run":
                    print(f"     [DRY RUN] Would publish to page {dest_id} scheduled for {sched_str}")
                    published_id = f"dry_run_{post_id}"
                else:
                    published_id = publish_to_facebook(
                        dest_page_id=dest_id,
                        access_token=token,
                        image_path=rendered_file,
                        caption=ai_data["rewritten_caption"],
                        scheduled_publish_time=target_publish_ts
                    )
                    print(f"     [SUCCESS] Published to Meta Graph API ID: {published_id}")

                # Update state & counters
                processed_ids.append(post_id)
                channel_stat["count"] += 1
                channel_stat["timestamps"].append(datetime.now(timezone.utc).isoformat())
                channel_stat["last_published_time"] = target_publish_ts
                last_pub_time = target_publish_ts
                accumulated_gap_seconds += effective_gap_seconds

                if os.path.exists(rendered_file):
                    os.remove(rendered_file)

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
