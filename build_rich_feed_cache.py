import os
import json
import base64
import cv2
from datetime import datetime, timezone
from modules.ingestion import fetch_facebook_public_posts
from modules.image_cleaner import download_image
from modules.llm_transformer import smart_heuristic_headline

def build_rich_feed_cache(source_url="https://www.facebook.com/netflixdailyupdates", limit=15, cache_path="feed_cache.json"):
    print(f"Ingesting live posts from {source_url} (limit {limit})...")
    posts = fetch_facebook_public_posts(source_url, limit=limit)
    print(f"Retrieved {len(posts)} raw posts from Facebook.")

    enriched_posts = []
    for idx, p in enumerate(posts):
        print(f"[{idx+1}/{len(posts)}] Processing post {p.get('post_id')}...")
        img_url = p.get("image_url")
        b64_str = ""

        if img_url:
            try:
                raw_img = download_image(img_url)
                if raw_img is not None:
                    h, w = raw_img.shape[:2]
                    target_w = 480
                    target_h = int(h * (target_w / w))
                    thumb = cv2.resize(raw_img, (target_w, target_h), interpolation=cv2.INTER_AREA)
                    _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    b64_str = "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")
                    print(f"       Generated thumbnail: {target_w}x{target_h}px ({len(b64_str)} bytes)")
            except Exception as e:
                print(f"       Failed to download/thumbnail image: {e}")

        # Generate policy-compliant rewritten caption and headline
        ai_data = smart_heuristic_headline(p.get("caption", ""))

        enriched_post = {
            "post_id": p.get("post_id"),
            "photo_id": p.get("photo_id"),
            "caption_fingerprint": p.get("caption_fingerprint"),
            "caption": p.get("caption", ""),
            "rewritten_caption": ai_data.get("rewritten_caption", ""),
            "headline": ai_data.get("headline", ""),
            "image_url": img_url,
            "preview_data_url": b64_str,
            "created_time": p.get("created_time", int(datetime.now(timezone.utc).timestamp())),
            "source_gap_hours": p.get("source_gap_hours", 1.0),
            "source_tag": p.get("source_tag", "Netflix Fans")
        }
        enriched_posts.append(enriched_post)

    payload = {
        "success": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "page": source_url,
        "count": len(enriched_posts),
        "posts": enriched_posts
    }

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Successfully wrote {len(enriched_posts)} enriched posts to {cache_path}!")
    return payload

if __name__ == "__main__":
    build_rich_feed_cache()
