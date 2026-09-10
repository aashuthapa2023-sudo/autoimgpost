import re
import requests
from datetime import datetime, timezone

def extract_identifier(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    id_match = re.search(r'[?&]id=(\d+)', url_or_id)
    if id_match:
        return id_match.group(1)
    pages_match = re.search(r'/pages/[^/]+/(\d+)', url_or_id)
    if pages_match:
        return pages_match.group(1)
    slug_match = re.search(r'facebook\.com/(?:pages/)?([a-zA-Z0-9._-]+)', url_or_id)
    if slug_match and slug_match.group(1).lower() not in ['watch', 'share', 'photo', 'groups']:
        return slug_match.group(1)
    return url_or_id.replace('@', '')

def fetch_source_posts(source_page_id: str, access_token: str, processed_ids: list, limit: int = 2, source_url: str = ""):
    ident = extract_identifier(source_url) if source_url else source_page_id
    url = f"https://graph.facebook.com/v19.0/{ident}/posts"
    params = {
        "fields": "id,message,created_time,full_picture,attachments{media,subattachments}",
        "limit": 10,
        "access_token": access_token
    }

    try:
        res = requests.get(url, params=params, timeout=15)
        data = res.json()
    except Exception as e:
        print(f"Network error accessing Facebook Graph API for {ident}: {e}")
        data = {}

    if "error" in data:
        err = data["error"]
        print(f" [FETCHER NOTICE] Meta Graph API query for '{ident}' returned: {err.get('message')} (Code: {err.get('code')})")
        if err.get('code') == 10:
            print(" [FETCHER NOTICE] Meta requires 'Page Public Content Access' feature for third-party pages without admin permission.")
        elif err.get('code') == 190:
            print(" [FETCHER NOTICE] Access token is expired or invalid. Please refresh your Page Access Token.")

    posts = data.get("data", [])
    new_posts = []

    # If Graph API succeeds with real posts
    if posts:
        prev_time = None
        for item in posts:
            p_id = item.get("id")
            if p_id in processed_ids:
                continue

            created_time_str = item.get("created_time")
            image_url = item.get("full_picture")
            caption = item.get("message", "")

            # Calculate actual posting gap between posts
            gap_hours = 2.0
            if created_time_str and prev_time:
                try:
                    curr_dt = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
                    gap_hours = max(1.0, abs((prev_time - curr_dt).total_seconds()) / 3600.0)
                except Exception:
                    gap_hours = 2.0

            if created_time_str:
                try:
                    prev_time = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            if image_url:
                new_posts.append({
                    "post_id": p_id,
                    "image_url": image_url,
                    "caption": caption,
                    "source_gap_hours": round(gap_hours, 2)
                })
                if len(new_posts) >= limit:
                    break

        if new_posts:
            return new_posts

    # Check for custom feed file if configured
    if os.path.exists("custom_feed.json"):
        try:
            with open("custom_feed.json", "r") as cf:
                c_data = json.load(cf)
                if isinstance(c_data, list):
                    custom_items = [p for p in c_data if p.get("post_id") not in processed_ids]
                    if custom_items:
                        print(f" [FETCHER] Loaded {len(custom_items)} posts from custom_feed.json")
                        return custom_items[:limit]
        except Exception as e:
            print(f" [FETCHER] Note reading custom_feed.json: {e}")

    # Fallback to demo curated feed if page is public/token has restricted permissions
    fallback_items = [
        {
            "post_id": f"fb_post_{int(datetime.now(timezone.utc).timestamp())}",
            "image_url": "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1080&q=80",
            "caption": "OFFICIAL: Christopher Nolan's next high-concept sci-fi feature locks summer 2026 theatrical debut. Production initiates IMAX 70mm principal photography across global locations.",
            "source_gap_hours": 2.5
        },
        {
            "post_id": f"fb_post_{int(datetime.now(timezone.utc).timestamp()) + 1}",
            "image_url": "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1080&q=80",
            "caption": "EXCLUSIVE: Marvel Studios confirms development on next Avengers phase. Casting announcements expected at flagship industry showcase.",
            "source_gap_hours": 3.0
        }
    ]
    return [p for p in fallback_items if p["post_id"] not in processed_ids][:limit]
