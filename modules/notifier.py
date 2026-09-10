import os
import requests

def send_telegram_alert(phase: str, channel_name: str, post_id: str, error_message: str, traceback_str: str = None):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return

    text = f"""🚨 <b>FACEBOOK PIPELINE ALERT</b>
━━━━━━━━━━━━━━━━━━━━
📌 <b>Channel:</b> <code>{channel_name}</code>
🆔 <b>Post:</b> <code>{post_id}</code>
⚙️ <b>Phase:</b> <code>{phase}</code>
⚠️ <b>Error:</b> <code>{error_message}</code>
━━━━━━━━━━━━━━━━━━━━"""

    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass
