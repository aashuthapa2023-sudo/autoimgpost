from urllib.parse import urlparse


def get_source_layout(channel, post):
    """Apply explicit source layouts only within their destination channel."""
    source = str(post.get("source_page_url", ""))
    parsed = urlparse(source)
    slug = parsed.path.strip('/').split('/')[0].lower()
    if parsed.hostname not in ("facebook.com", "www.facebook.com", "m.facebook.com"):
        slug = ""
    overrides = channel.get("source_layouts", {})
    layout = overrides.get(slug, {})
    position = layout.get("text_position", "bottom")
    result = {"text_position": position if position in ("top", "bottom") else "bottom"}
    logo_position = layout.get("logo_position", "with-text")
    if logo_position in ("top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right"):
        result["logo_position"] = logo_position
    if result["text_position"] == "top" and "source_header_fraction" in layout:
        result["source_header_fraction"] = max(0.2, min(0.45, float(layout["source_header_fraction"])))
    return result
