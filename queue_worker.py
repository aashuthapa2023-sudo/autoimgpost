"""Use the shared pipeline for every page; retain old queued posters for review."""
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from main import run_pipeline

QUEUE_FILE = "queue_nepal_speaks.json"


def process_queue_or_poll():
    queue_path = Path(QUEUE_FILE)
    if queue_path.exists():
        try:
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            queue = None
        if queue:
            archive = queue_path.with_name("review_queue_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f") + ".json")
            queue_path.rename(archive)
            queue_path.write_text("[]", encoding="utf-8")
            print("Older queued posters saved for review; regenerate through the checked pipeline.")
    run_pipeline(mode="run", target_channel="all")


def run_loop():
    while True:
        try:
            process_queue_or_poll()
        except Exception:
            traceback.print_exc()
        time.sleep(900)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        process_queue_or_poll()
    else:
        run_loop()
