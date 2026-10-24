import os
import json
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

# utf-8-sig handles a .env file whether or not it has a BOM at the start
# (Windows PowerShell's Out-File adds one; this makes it not matter)
load_dotenv(encoding="utf-8-sig")

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY not found. Check that .env is in the project root "
        "(same folder as app.py, not inside templates/ or venv/) and contains "
        "exactly one line: GEMINI_API_KEY=your_key_here"
    )

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-3.6-flash"

# Deterministic settings - same input always gives the same score, every time.
# Without this, Gemini's default randomness means asking the same question
# twice can legitimately return different answers.
GENERATION_CONFIG = types.GenerateContentConfig(
    temperature=0,
    top_p=1,
    top_k=1,
)

DETECTION_PROMPT = """You are an AI-text detection assistant analyzing a screenshot of a chat conversation.

Steps:
1. Look at the screenshot and figure out whether messages from BOTH people in the conversation are visible, or only the OTHER person's messages (not the user's own sent messages).
2. Extract the OTHER person's most recent message text exactly as written. Never analyze or extract the user's own sent messages.
3. Analyze the writing style of that extracted message for signs of AI generation: unnaturally uniform sentence length, no contractions, overly complete/formal answers, generic phrasing, no typos or filler words - versus casual human traits like slang, typos, or short fragments.

Return ONLY valid JSON in this exact structure, no markdown, no extra text:
{
  "extracted_text": "the other person's message, exactly as written",
  "chat_sides_detected": "both" | "other_only" | "unclear",
  "ai_likelihood": <integer 0-100>,
  "reasoning": ["short point 1", "short point 2"],
  "confidence": "low" | "medium" | "high"
}

chat_sides_detected meaning:
- "both": messages from the user AND the other person are visible in the screenshot
- "other_only": only the other person's messages/notifications are visible
- "unclear": cannot confidently tell who sent what

If you cannot find a clear message from another person in the screenshot, set extracted_text to "", chat_sides_detected to "unclear", and confidence to "low".
"""

TEXT_DETECTION_PROMPT = """You are an AI-text detection assistant analyzing a single chat message that was pasted directly by the user (not extracted from an image).

Analyze the writing style of this message for signs of AI generation: unnaturally uniform sentence length, no contractions, overly complete/formal answers, generic phrasing, no typos or filler words - versus casual human traits like slang, typos, or short fragments.

Return ONLY valid JSON in this exact structure, no markdown, no extra text:
{
  "ai_likelihood": <integer 0-100>,
  "reasoning": ["short point 1", "short point 2"],
  "confidence": "low" | "medium" | "high"
}
"""


def analyze_screenshot(image_bytes: bytes, mime_type: str = "image/png") -> dict:
    """Send a chat screenshot to Gemini and get back a structured AI-likelihood verdict."""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                DETECTION_PROMPT,
            ],
            config=GENERATION_CONFIG,
        )

        raw_text = response.text.strip()
        cleaned = re.sub(r"^```json|```$", "", raw_text, flags=re.MULTILINE).strip()

        result = json.loads(cleaned)
        result["mock"] = False
        return result

    except json.JSONDecodeError:
        return {
            "mock": False,
            "error": "Gemini returned an unexpected format. Try again.",
            "extracted_text": "",
            "chat_sides_detected": "unclear",
            "ai_likelihood": 0,
            "reasoning": ["Could not parse model response."],
            "confidence": "low",
        }
    except Exception as e:
        return {
            "mock": False,
            "error": f"Gemini API call failed: {str(e)}",
            "extracted_text": "",
            "chat_sides_detected": "unclear",
            "ai_likelihood": 0,
            "reasoning": [],
            "confidence": "low",
        }


def analyze_text_message(text: str) -> dict:
    """Send raw pasted text (no image, no OCR needed) to Gemini for an AI-likelihood verdict."""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[TEXT_DETECTION_PROMPT, f"\nMessage to analyze:\n{text}"],
            config=GENERATION_CONFIG,
        )

        raw_text = response.text.strip()
        cleaned = re.sub(r"^```json|```$", "", raw_text, flags=re.MULTILINE).strip()

        result = json.loads(cleaned)
        result["mock"] = False
        result["extracted_text"] = text
        return result

    except json.JSONDecodeError:
        return {
            "mock": False,
            "error": "Gemini returned an unexpected format. Try again.",
            "extracted_text": text,
            "ai_likelihood": 0,
            "reasoning": ["Could not parse model response."],
            "confidence": "low",
        }
    except Exception as e:
        return {
            "mock": False,
            "error": f"Gemini API call failed: {str(e)}",
            "extracted_text": text,
            "ai_likelihood": 0,
            "reasoning": [],
            "confidence": "low",
        }