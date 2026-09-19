import os
import sys
import json
import time
import traceback
from datetime import datetime, timezone

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.publisher import publish_to_facebook
from main import run_pipeline, load_state, save_state

QUEUE_FILE = "queue_nepal_speaks.json"
PAGE_ID = "963003030237850"
TOKEN = "EAAXSklef1o0BSm1GMjkd8YpWmL0hzIiTklmzrwkkP0h5iCbgKEXQi7b3aB6aWKoHgsguAZC99SgKs65YWk9PdRmKi75Qt0Q8YNeiJtyyWJhjmgyvwWNGbyeIOToXDVLsC5FJKqtzCPGdoOSBsB6A9tf5FZCNMr78QUQuSGANcTUBWwyVUGSMRLik428GXBp2bfgFzw"

def process_queue_or_poll():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Checking Nepal Speaks Auto-Publish Queue ---")
    
    queue = []
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
        except Exception as e:
            print(f"Error loading {QUEUE_FILE}: {e}")
            queue = []

    if queue:
        next_item = queue.pop(0)
        print(f"Found queued post: '{next_item.get('title')}' (ID: {next_item.get('id')})")
        img_path = next_item.get("image_path")
        caption = next_item.get("caption")

        if os.path.exists(img_path):
            try:
                print(f"Publishing to Nepal Speaks Facebook Page ({PAGE_ID})...")
                fb_id = publish_to_facebook(
                    dest_page_id=PAGE_ID,
                    access_token=TOKEN,
                    image_path=img_path,
                    caption=caption
                )
                print(f"SUCCESS! Published queued post. Meta Graph API Post ID: {fb_id}")

                # Update state.json
                state = load_state()
                now_ts = int(time.time())
                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                if "nepal_speaks" not in state["processed_ids"]:
                    state["processed_ids"]["nepal_speaks"] = []
                
                item_id = str(next_item.get("id"))
                if item_id and item_id not in state["processed_ids"]["nepal_speaks"]:
                    state["processed_ids"]["nepal_speaks"].append(item_id)
                if item_id and item_id not in state["global_processed_ids"]:
                    state["global_processed_ids"].append(item_id)

                if "nepal_speaks" not in state["daily_stats"]:
                    state["daily_stats"]["nepal_speaks"] = {"date": today_str, "count": 0, "timestamps": [], "last_published_time": 0}
                
                ns_stats = state["daily_stats"]["nepal_speaks"]
                if ns_stats.get("date") != today_str:
                    ns_stats["date"] = today_str
                    ns_stats["count"] = 0
                    ns_stats["timestamps"] = []
                ns_stats["count"] += 1
                ns_stats["last_published_time"] = now_ts
                ns_stats["timestamps"].append(datetime.now(timezone.utc).isoformat())

                save_state(state)
                print(f"Updated state.json. Remaining in queue: {len(queue)}")

            except Exception as ex:
                print(f"Error publishing queued post: {ex}")
                traceback.print_exc()
                # Re-insert item at front if failed
                queue.insert(0, next_item)

        # Save remaining queue
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)

    else:
        print("Queue is empty. Running main pipeline for 'nepal_speaks' to check for any fresh source posts from HimaliMedia...")
        try:
            run_pipeline(mode="run", target_channel="nepal_speaks")
        except Exception as ex:
            print(f"Error running pipeline: {ex}")
            traceback.print_exc()

def run_loop():
    print("===================================================================")
    print("  Nepal Speaks 30-Minute Interval Automation Worker Started")
    print("  Post 1 was published live. Next queued post in 30 minutes.")
    print("===================================================================")
    while True:
        print(f"\nSleeping for 30 minutes (1800s) until next publication cycle...")
        time.sleep(1800)
        try:
            process_queue_or_poll()
        except Exception as e:
            print(f"Loop iteration error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        process_queue_or_poll()
    else:
        run_loop()
