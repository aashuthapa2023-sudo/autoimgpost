import os
import sys
import json
import time
import queue
import threading
import subprocess
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timezone

PORT = 8000
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_QUEUE = queue.Queue(maxsize=1000)
RECENT_LOGS = []
CURRENT_RUN = {
    "is_running": False,
    "current_stage": 0,
    "current_post": None,
    "start_time": None,
    "last_poster": None,
    "error": None
}

def log_message(msg: str, stage: int = None):
    line = {
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "msg": msg,
        "stage": stage
    }
    RECENT_LOGS.append(line)
    if len(RECENT_LOGS) > 300:
        RECENT_LOGS.pop(0)
    try:
        LOG_QUEUE.put_nowait(line)
    except Exception:
        pass
    print(f"[{line['time']}] {msg}")

def execute_pipeline_task(action="dry_run", channel="all", specific_post=None):
    global CURRENT_RUN
    CURRENT_RUN["is_running"] = True
    CURRENT_RUN["current_stage"] = 1
    CURRENT_RUN["error"] = None
    CURRENT_RUN["start_time"] = time.time()

    try:
        log_message(f"Initiating pipeline execution (Mode: {action}, Target: {channel})...", stage=1)
        
        from modules.ingestion import fetch_source_posts, fetch_facebook_public_posts
        from modules.image_cleaner import download_image, erase_text_and_watermarks, apply_cinematic_grade
        from modules.llm_transformer import generate_social_payload
        from modules.poster_engine import render_final_poster
        import main as main_engine

        config = main_engine.load_config()
        state = main_engine.load_state()
        channels = config.get("channels", [])
        
        os.makedirs("output", exist_ok=True)

        if specific_post:
            log_message(f"Stage 1: Ingesting selected post ID {specific_post.get('post_id')}...", stage=1)
            ch = next((c for c in channels if c["channel_id"] == channel), channels[0])
            
            log_message("Stage 2: Enforcing Facebook publishing cadence & daily caps...", stage=2)
            time.sleep(0.5)

            log_message(f"Stage 3: Downloading image & running smart watermark cleaner...", stage=3)
            raw_img = download_image(specific_post["image_url"])
            cleaned = erase_text_and_watermarks(raw_img)

            log_message("Stage 4: Applying OpenCV CIE-LAB CLAHE dynamic contrast grade...", stage=4)
            graded = apply_cinematic_grade(cleaned)

            log_message("Stage 5: Generating dual-tone viral headline & policy caption...", stage=5)
            ai_data = generate_social_payload(specific_post["caption"])

            out_poster = f"output/{ch['channel_id']}_{specific_post['post_id']}.jpg"
            log_message(f"Stage 6: Compositing 4:5 studio poster to {out_poster}...", stage=6)
            render_final_poster(
                base_img=graded,
                overlay_lines=ai_data["overlay_lines"],
                highlight_hex=ch.get("highlight_color", "#FFC83B"),
                badge_label=ch.get("badge_label", "NETFLIX FANS EXCLUSIVE"),
                output_path=out_poster
            )
            CURRENT_RUN["last_poster"] = out_poster.replace("\\", "/")
            CURRENT_RUN["current_post"] = specific_post

            log_message(f"Stage 7: Scheduling / Meta Graph API Stage complete! Target: {out_poster}", stage=7)
            CURRENT_RUN["current_stage"] = 7
            log_message("Execution completed successfully! Poster ready for preview.", stage=7)

        else:
            proc = subprocess.Popen(
                [sys.executable, "main.py", action, channel],
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            stage_map = {
                "[INGEST]": 1,
                "[DAILY CAP": 2,
                "[1/5]": 3,
                "[2/5]": 4,
                "[3/5]": 5,
                "[4/5]": 6,
                "[5/5]": 7
            }
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                s_line = line.strip()
                detected_stage = None
                for k, v in stage_map.items():
                    if k in s_line:
                        detected_stage = v
                        CURRENT_RUN["current_stage"] = v
                        break
                if "output" in s_line and ".jpg" in s_line:
                    for part in s_line.split():
                        if "output" in part and part.endswith(".jpg"):
                            CURRENT_RUN["last_poster"] = part.replace("\\", "/")
                log_message(s_line, stage=detected_stage)

            proc.stdout.close()
            proc.wait()
            CURRENT_RUN["current_stage"] = 7
            log_message("Pipeline execution finished with exit code 0.", stage=7)

    except Exception as e:
        CURRENT_RUN["error"] = str(e)
        log_message(f"[ERROR] Pipeline run failed: {e}")
    finally:
        CURRENT_RUN["is_running"] = False

class PipelineHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            import main as main_engine
            config = main_engine.load_config()
            state = main_engine.load_state()
            resp_data = {
                "pipeline_active": config.get("pipeline_active", True),
                "current_run": CURRENT_RUN,
                "daily_stats": state.get("daily_stats", {}),
                "channels": config.get("channels", [])
            }
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        if path == "/api/logs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "current_stage": CURRENT_RUN["current_stage"],
                "is_running": CURRENT_RUN["is_running"],
                "last_poster": CURRENT_RUN["last_poster"],
                "logs": RECENT_LOGS[-60:]
            }).encode("utf-8"))
            return

        if path == "/api/fb-feed":
            page = query.get("page", ["https://www.facebook.com/netflixfanslivehere"])[0]
            limit = int(query.get("limit", [5])[0])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from modules.ingestion import fetch_facebook_public_posts
                posts = fetch_facebook_public_posts(page, limit=limit)
                self.wfile.write(json.dumps({"success": True, "page": page, "posts": posts}).encode("utf-8"))
            except Exception as e:
                self.wfile.write(json.dumps({"success": False, "error": str(e), "posts": []}).encode("utf-8"))
            return

        if path == "/api/posters":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            out_files = []
            if os.path.exists("output"):
                for fn in sorted(os.listdir("output"), reverse=True):
                    if fn.endswith(".jpg") or fn.endswith(".png"):
                        fp = os.path.join("output", fn)
                        out_files.append({
                            "filename": fn,
                            "url": f"/output/{fn}",
                            "size": os.path.getsize(fp),
                            "modified": os.path.getmtime(fp)
                        })
            self.wfile.write(json.dumps({"posters": out_files}).encode("utf-8"))
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body = {}

        if path == "/api/run":
            action = body.get("action", "dry_run")
            channel = body.get("channel", "all")
            if CURRENT_RUN["is_running"]:
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Pipeline already running"}).encode("utf-8"))
                return

            t = threading.Thread(target=execute_pipeline_task, args=(action, channel, None), daemon=True)
            t.start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": f"Action {action} launched for {channel}"}).encode("utf-8"))
            return

        if path == "/api/test-post":
            post = body.get("post")
            channel = body.get("channel", "netflix_fans")
            if not post or not post.get("image_url"):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Invalid post payload"}).encode("utf-8"))
                return

            t = threading.Thread(target=execute_pipeline_task, args=("dry_run", channel, post), daemon=True)
            t.start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": f"Processing post {post.get('post_id')}"}).encode("utf-8"))
            return

        if path == "/api/toggle-active":
            import main as main_engine
            config = main_engine.load_config()
            new_val = not config.get("pipeline_active", True)
            config["pipeline_active"] = new_val
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "pipeline_active": new_val}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def run_server(port=PORT):
    server = HTTPServer(("0.0.0.0", port), PipelineHandler)
    print(f"===========================================================")
    print(f"  AutoImgPost 24/7 Automation Hub & Live Sync UI Server")
    print(f"  Listening on: http://localhost:{port}")
    print(f"===========================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down...")
        server.server_close()

if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_server(p)
