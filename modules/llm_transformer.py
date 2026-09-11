import os
import json
import re
import requests

def build_system_prompt() -> str:
    return """You are an expert Facebook entertainment page editor creating high-compliance 4:5 visual posts.
STRICT META CONTENT POLICIES:
1. NO ENGAGEMENT BAIT: Never ask for likes, shares, comments, or tag friends.
2. NO CLICKBAIT: State facts upfront without sensationalist withholding.
3. TRANSFORMATIVE COMMENTARY: Provide context, key details, and original analysis.
4. SOURCING: Always add clear attribution (e.g. Source: Official reports).

Return strictly JSON with:
{
  "overlay_lines": [
    [{"text": "WHITE WORDS ", "type": "white"}, {"text": "HIGHLIGHT WORD", "type": "highlight"}],
    [{"text": "WHITE WORDS ", "type": "white"}, {"text": "HIGHLIGHT WORD", "type": "highlight"}]
  ],
  "rewritten_caption": "Full policy-compliant caption text..."
}"""

def smart_heuristic_headline(raw_caption: str) -> dict:
    """Smart zero-network heuristic that parses names, dates, and keywords into dual-tone lines."""
    clean = raw_caption.strip()
    first_sentence = clean.split(".")[0].split("\n")[0].strip()
    
    # Check for keywords
    keywords = ["CANCELLED", "CONFIRMED", "OFFICIAL", "REVEALED", "RETURNING", "HONORED", "WINS", "REVIEWS", "UPDATE", "PREMIERES", "TRAILER"]
    found_kw = "CONFIRMED"
    upper_c = clean.upper()
    for kw in keywords:
        if kw in upper_c:
            found_kw = kw
            break

    # Extract subject
    words = [w for w in re.split(r'\s+', first_sentence) if w]
    if len(words) >= 6:
        line1_words = words[:3]
        line2_words = words[3:7]
        line1 = [{"text": " ".join(line1_words).upper() + " ", "type": "white"}, {"text": found_kw, "type": "highlight"}]
        line2 = [{"text": " ".join(line2_words).upper() + " ", "type": "white"}, {"text": "DETAILS", "type": "highlight"}]
    else:
        line1 = [{"text": "ENTERTAINMENT NEWS ", "type": "white"}, {"text": found_kw, "type": "highlight"}]
        line2 = [{"text": "OFFICIAL REPORT ", "type": "white"}, {"text": "DETAILS", "type": "highlight"}]

    rewritten = f"{first_sentence}\n\nKey Highlights & Breakdown:\n• Verified entertainment briefings confirm production trajectory.\n• Industry tracking indicates massive interest across major streaming communities.\n\nSource: Verified page briefings & industry updates.\n\n#Netflix #EntertainmentNews #StreamingTrends"
    return {
        "overlay_lines": [line1, line2],
        "rewritten_caption": rewritten
    }

def generate_social_payload(raw_caption: str) -> dict:
    prompt = build_system_prompt()

    # Tier 1: Groq Cloud
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": f"Raw post: {raw_caption}"}
                    ],
                    "response_format": {"type": "json_object"}
                },
                timeout=12
            )
            if res.status_code == 200:
                return json.loads(res.json()["choices"][0]["message"]["content"])
        except Exception:
            pass

    # Tier 2: Google AI Studio (Gemini)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{prompt}\n\nRaw post: {raw_caption}",
                config={"response_mime_type": "application/json"}
            )
            return json.loads(resp.text)
        except Exception:
            pass

    # Tier 3: OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
                json={
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": f"Raw post: {raw_caption}"}
                    ]
                },
                timeout=15
            )
            if res.status_code == 200:
                txt = res.json()["choices"][0]["message"]["content"]
                return json.loads(txt[txt.find("{"):txt.rfind("}")+1])
        except Exception:
            pass

    # Tier 4: Smart Heuristic
    return smart_heuristic_headline(raw_caption)
