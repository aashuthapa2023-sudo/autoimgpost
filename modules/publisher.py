import requests

def publish_to_facebook(dest_page_id: str, access_token: str, image_path: str, caption: str, scheduled_publish_time: int = None) -> str:
    """
    Publishes the generated 4:5 image and caption to Facebook Page INSTANTLY.
    Meta Graph API scheduling is disabled to guarantee immediate live delivery.
    """
    url = f"https://graph.facebook.com/v19.0/{dest_page_id}/photos"
    
    data = {
        "caption": caption,
        "access_token": access_token,
        "published": "true"
    }

    with open(image_path, "rb") as img_file:
        files = {"source": img_file}
        resp = requests.post(url, data=data, files=files, timeout=30)
        res_json = resp.json()

    if "id" in res_json:
        return res_json["id"]
    elif "error" in res_json:
        raise RuntimeError(f"Facebook Graph API Error: {res_json['error'].get('message')}")
    return "UNKNOWN_ID"

