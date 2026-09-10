# Automated Facebook Content Pipeline (100% Free & Unlimited Architecture)

Target Repository: **https://github.com/aashuthapa2023-sudo/autoimgpost.git**

## Zero-Cost Engineering Architecture

| Component | Unlimited Free Technology | Why It Never Charges |
|---|---|---|
| **Compute Runner** | Public GitHub Repository Actions | 100% free and unlimited runner minutes for public repos. |
| **Watermark Erasing** | Local EasyOCR + OpenCV INPAINT_TELEA | Executes natively on runner CPU in ~2s with zero external API calls. |
| **Upscaling & Grading**| OpenCV CLAHE + Pillow Lanczos Filter | Native image processing; runs locally with zero rate limits. |
| **Text & Copy AI** | Groq ➔ Google AI Studio ➔ OpenRouter :free ➔ CPU Heuristic | Multi-tier failover cycling through free developer allowances (~16,000+ free requests/day). |
| **Publisher** | Meta Graph API (Long-Lived System Token) | Free up to 200 requests/hour per page. |

## Strict Safety & Policy Rules

1. **Max 15 Images Per Day Per Page**:
   - The engine tracks `daily_stats` in `state.json`.
   - Each page stops publishing automatically after 15 images in any 24-hour UTC window to preserve distribution algorithms and prevent spam penalties.

2. **At Least 1 Hour Gap Per Post**:
   - Consecutive posts on any page are strictly spaced by at least 3600 seconds (1.0 hour).
   - If the source page posts rapidly (e.g. 5 posts in 20 minutes), the destination page schedules them cleanly spaced across the day.

3. **Master Auto Start / Stop Switch**:
   - Toggle `pipeline_active: true / false` in `config.json` or the web UI.
   - Paused runs exit gracefully without touching Graph API.

## Repository Secrets Required in GitHub Actions

Set these in **Settings ➔ Secrets and variables ➔ Actions**:

```
GROQ_API_KEY          (Optional: Tier 1 free developer LPU tier)
GEMINI_API_KEY        (Optional: Tier 2 Google AI Studio free tier)
OPENROUTER_API_KEY    (Optional: Tier 3 :free open-source models)
TELEGRAM_BOT_TOKEN    (Optional: Real-time pipeline failure watchdog alerts)
TELEGRAM_CHAT_ID      (Optional: Telegram recipient chat ID)
FB_TOKEN_CINEMA       (Required: Meta Page Access Token for CineVerse)
FB_TOKEN_GAMING       (Required: Meta Page Access Token for NextGen Gaming)
FB_TOKEN_TECH         (Required: Meta Page Access Token for AI Frontier)
```
