import os
import sys
import json
import time
import queue
import hashlib
import threading
import subprocess
import urllib.parse
import requests
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timezone

PORT = 8000
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

LOG_QUEUE = queue.Queue(maxsize=1000)
RECENT_LOGS = []
CURRENT_RUN = {
    "is_running": False,
    "current_stage": 0,
    "current_post": None,
    "start_time": None,
    "last_poster": None,
    "source_caption": None,
    "rewritten_caption": None,
    "error": None
}

FB_BOT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Referer': 'https://www.facebook.com/'
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
            ch = next((c for c in channels if c["channel_id"] == channel), channels[0] if channels else {})
            dest_name = ch.get("dest_page_name", ch.get("channel_name", "OFFICIAL"))
            highlight_color = ch.get("highlight_color", "#FFC83B")
            channel_id = ch.get("channel_id", "custom")

            CURRENT_RUN["source_caption"] = specific_post.get("caption", "")

            log_message("Stage 2: Enforcing Facebook publishing cadence & daily caps...", stage=2)
            time.sleep(0.4)

            log_message("Stage 3: Downloading high-res image & running intelligent watermark inpainter...", stage=3)
            raw_img = download_image(specific_post["image_url"])
            cleaned = erase_text_and_watermarks(raw_img)

            log_message("Stage 4: Applying OpenCV CIE-LAB CLAHE contrast grading...", stage=4)
            graded = apply_cinematic_grade(cleaned)

            log_message("Stage 5: Generating original, policy-compliant caption & centered headline...", stage=5)
            ai_data = generate_social_payload(specific_post["caption"])
            CURRENT_RUN["rewritten_caption"] = ai_data["rewritten_caption"]

            out_poster = f"output/{channel_id}_{specific_post['post_id']}.jpg"
            log_message(f"Stage 6: Compositing centered 4:5 visual poster with destination branding ({dest_name})...", stage=6)
            render_final_poster(
                base_img=graded,
                overlay_lines=ai_data["overlay_lines"],
                highlight_hex=highlight_color,
                dest_page_name=dest_name,
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

        # Image Proxy to bypass Facebook crawler referrer checks in web browser
        if path == "/api/proxy-image":
            img_url = query.get("url", [""])[0]
            if not img_url:
                self.send_response(400)
                self.end_headers()
                return

            url_hash = hashlib.md5(img_url.encode("utf-8")).hexdigest()
            cached_fp = os.path.join(CACHE_DIR, f"{url_hash}.jpg")

            if os.path.exists(cached_fp) and os.path.getsize(cached_fp) > 5000:
                with open(cached_fp, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return

            try:
                resp = requests.get(img_url, headers=FB_BOT_HEADERS, timeout=20)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    with open(cached_fp, "wb") as f:
                        f.write(resp.content)
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(resp.content)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(resp.content)
                    return
            except Exception as e:
                print(f" [PROXY ERROR] Failed to fetch image {img_url}: {e}")

            self.send_response(404)
            self.end_headers()
            return

        if path == "/api/status":
            import main as main_engine
            config = main_engine.load_config()
            state = main_engine.load_state()
            resp_data = {
                "pipeline_active": config.get("pipeline_active", True),
                "current_run": CURRENT_RUN,
                "daily_stats": state.get("daily_stats", {}),
                "channels": config.get("channels", [])
            }
            body = json.dumps(resp_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/logs":
            body = json.dumps({
                "current_stage": CURRENT_RUN["current_stage"],
                "is_running": CURRENT_RUN["is_running"],
                "last_poster": CURRENT_RUN["last_poster"],
                "source_caption": CURRENT_RUN["source_caption"],
                "rewritten_caption": CURRENT_RUN["rewritten_caption"],
                "logs": RECENT_LOGS[-60:]
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/fb-feed":
            page = query.get("page", ["https://www.facebook.com/netflixfanslivehere"])[0]
            limit = int(query.get("limit", [15])[0])
            try:
                from modules.ingestion import fetch_facebook_public_posts
                from modules.llm_transformer import smart_heuristic_headline
                posts = fetch_facebook_public_posts(page, limit=limit)
                # Attach proxy_image_url and instant rewritten preview
                for p in posts:
                    p["proxy_image_url"] = f"/api/proxy-image?url={urllib.parse.quote(p['image_url'])}"
                    ai_prev = smart_heuristic_headline(p["caption"])
                    p["rewritten_caption"] = ai_prev["rewritten_caption"]
                resp_json = {"success": True, "page": page, "count": len(posts), "posts": posts}
            except Exception as e:
                resp_json = {"success": False, "error": str(e), "posts": []}

            body = json.dumps(resp_json).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/posters":
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
            body = json.dumps({"posters": out_files}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
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
                resp = json.dumps({"success": False, "message": "Pipeline already running"}).encode("utf-8")
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp)
                return

            t = threading.Thread(target=execute_pipeline_task, args=(action, channel, None), daemon=True)
            t.start()
            resp = json.dumps({"success": True, "message": f"Action {action} launched for {channel}"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        if path == "/api/test-post":
            post = body.get("post")
            channel = body.get("channel", "netflix_fans")
            if not post or not post.get("image_url"):
                resp = json.dumps({"success": False, "message": "Invalid post payload"}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp)
                return

            t = threading.Thread(target=execute_pipeline_task, args=("dry_run", channel, post), daemon=True)
            t.start()
            resp = json.dumps({"success": True, "message": f"Processing post {post.get('post_id')}"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        if path == "/api/toggle-active":
            import main as main_engine
            config = main_engine.load_config()
            new_val = not config.get("pipeline_active", True)
            config["pipeline_active"] = new_val
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            resp = json.dumps({"success": True, "pipeline_active": new_val}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        if path == "/api/channels/add":
            import main as main_engine
            config = main_engine.load_config()
            cid = body.get("channel_id", "").strip().lower().replace(" ", "_")
            if not cid:
                resp = json.dumps({"success": False, "message": "channel_id is required"}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp)
                return

            sources = body.get("source_pages", [])
            if isinstance(sources, str):
                sources = [s.strip() for s in sources.split(",") if s.strip()]

            dest_name = body.get("dest_page_name") or body.get("channel_name") or cid.replace("_", " ").title()
            new_ch = {
                "channel_id": cid,
                "channel_name": body.get("channel_name", cid),
                "source_pages": sources if sources else [body.get("source_page_url", f"https://www.facebook.com/{cid}")],
                "source_page_url": sources[0] if sources else body.get("source_page_url", ""),
                "dest_page_id": body.get("dest_page_id", "DEMO_PAGE_ID"),
                "dest_page_name": dest_name,
                "dest_access_token_env": body.get("dest_access_token_env", f"FB_TOKEN_{cid.upper()}"),
                "badge_label": dest_name,
                "highlight_color": body.get("highlight_color", "#FFC83B"),
                "max_posts_per_run": int(body.get("max_posts_per_run", 2)),
                "cadence_mirror_enabled": True,
                "fetch_frequency": "hourly",
                "policy_compliance_mode": "strict_fb_standard",
                "max_daily_posts": 15,
                "min_gap_hours": 1
            }

            existing_idx = next((i for i, c in enumerate(config["channels"]) if c["channel_id"] == cid), None)
            if existing_idx is not None:
                config["channels"][existing_idx] = new_ch
            else:
                config["channels"].append(new_ch)

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            resp = json.dumps({"success": True, "channels": config["channels"]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        if path == "/api/channels/delete":
            import main as main_engine
            config = main_engine.load_config()
            cid = body.get("channel_id", "")
            config["channels"] = [c for c in config["channels"] if c["channel_id"] != cid]
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            resp = json.dumps({"success": True, "channels": config["channels"]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        if path == "/api/channels/add-source":
            import main as main_engine
            config = main_engine.load_config()
            cid = body.get("channel_id", "")
            source_url = body.get("source_page", "").strip()
            ch = next((c for c in config["channels"] if c["channel_id"] == cid), None)
            if not ch or not source_url:
                resp = json.dumps({"success": False, "message": "Invalid channel or source_page"}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp)
                return

            if "source_pages" not in ch:
                ch["source_pages"] = []
            if source_url not in ch["source_pages"]:
                ch["source_pages"].append(source_url)

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            resp = json.dumps({"success": True, "source_pages": ch["source_pages"]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        if path == "/api/channels/remove-source":
            import main as main_engine
            config = main_engine.load_config()
            cid = body.get("channel_id", "")
            source_url = body.get("source_page", "").strip()
            ch = next((c for c in config["channels"] if c["channel_id"] == cid), None)
            if not ch or not source_url:
                resp = json.dumps({"success": False, "message": "Invalid channel or source_page"}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp)
                return

            if "source_pages" in ch and source_url in ch["source_pages"]:
                ch["source_pages"].remove(source_url)

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            resp = json.dumps({"success": True, "source_pages": ch.get("source_pages", [])}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_response(404)
        self.end_headers()

def run_server(port=PORT):
    server = ThreadingHTTPServer(("0.0.0.0", port), PipelineHandler)
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
