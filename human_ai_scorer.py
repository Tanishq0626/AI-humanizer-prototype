import re
import statistics
import io

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# On Windows, uncomment and set this if tesseract isn't on your PATH:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def _sentence_lengths(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s for s in sentences if s]
    return [len(s.split()) for s in sentences]


def score_sentence_uniformity(text):
    """Very uniform sentence lengths lean AI-like; high variance leans human."""
    lengths = _sentence_lengths(text)
    if len(lengths) < 2:
        return 50  # not enough data to judge, stay neutral
    variance = statistics.pstdev(lengths)
    avg = statistics.mean(lengths)
    if avg == 0:
        return 50
    coefficient = variance / avg
    if coefficient < 0.15:
        return 85
    elif coefficient < 0.3:
        return 60
    elif coefficient < 0.5:
        return 40
    else:
        return 15


CONTRACTION_MARKERS = ["n't", "'re", "'ve", "'ll", "'d", "'m", "'s"]


def score_contractions(text):
    """No contractions at all leans AI-like; casual contractions lean human.
    Skipped entirely on short text, since there isn't enough signal to judge
    reliably, and this also avoids false positives on non-English/Hinglish
    text that has no English contractions to find in the first place."""
    words = text.split()
    if len(words) < 8:
        return 50
    contraction_count = sum(1 for w in words if any(c in w for c in CONTRACTION_MARKERS))
    ratio = contraction_count / len(words)
    if ratio == 0:
        return 80
    elif ratio < 0.03:
        return 55
    else:
        return 20


def score_punctuation_consistency(text):
    """Perfect terminal punctuation + capitalization leans AI-like; casual leans human."""
    stripped = text.strip()
    has_terminal_punct = bool(re.search(r'[.!?]$', stripped))
    exclam_count = text.count('!')
    ellipsis_count = text.count('...')
    lower_start = stripped[:1].islower() if stripped else False

    score = 50
    if has_terminal_punct:
        score += 15
    if lower_start:
        score -= 15
    if exclam_count > 1 or ellipsis_count > 0:
        score -= 10
    return max(0, min(100, score))


GENERIC_PHRASES = [
    "i appreciate", "i understand", "happy to help", "let me know if",
    "please feel free", "i would be happy", "thank you for reaching out",
    "i hope this helps", "as an ai",
]


def score_generic_phrasing(text):
    """Common AI-assistant stock phrases push the score up."""
    lowered = text.lower()
    hits = sum(1 for phrase in GENERIC_PHRASES if phrase in lowered)
    if hits == 0:
        return 40
    return min(100, 40 + hits * 25)


def generate_reasoning(scores: dict) -> list:
    """Turn the numeric sub-scores into short, human-readable reasoning lines."""
    lines = []

    su = scores.get("sentence_uniformity")
    if su is not None:
        if su >= 70:
            lines.append("Sentence lengths are unusually uniform, a common AI trait")
        elif su <= 30:
            lines.append("Sentence lengths vary a lot, typical of natural human writing")

    c = scores.get("contractions")
    if c is not None:
        if c >= 70:
            lines.append("No contractions used (e.g. 'do not' instead of 'don't'), leans AI-like")
        elif c <= 30:
            lines.append("Casual contractions used, leans human")

    p = scores.get("punctuation")
    if p is not None:
        if p >= 65:
            lines.append("Formal, complete punctuation and capitalization, leans AI-like")
        elif p <= 35:
            lines.append("Casual punctuation or capitalization, leans human")

    gp = scores.get("generic_phrasing")
    if gp is not None and gp >= 65:
        lines.append("Contains common AI-assistant stock phrases")

    if not lines:
        lines.append("No strong stylistic signals either way from the pattern check")

    return lines


def analyze_text(text: str) -> dict:
    """Pure-Python, no-API AI-likelihood scorer. Returns 0-100 + a per-signal breakdown + reasoning."""
    if not text or not text.strip():
        return {
            "heuristic_score": 50,
            "breakdown": {},
            "reasoning": ["No text was available to run the pattern check on"],
        }

    scores = {
        "sentence_uniformity": score_sentence_uniformity(text),
        "contractions": score_contractions(text),
        "punctuation": score_punctuation_consistency(text),
        "generic_phrasing": score_generic_phrasing(text),
    }

    final_score = round(sum(scores.values()) / len(scores))
    reasoning = generate_reasoning(scores)
    return {"heuristic_score": final_score, "breakdown": scores, "reasoning": reasoning}


def extract_text_from_image(image_bytes: bytes) -> str:
    """Local OCR - reads ALL visible text in the image. Cannot tell who sent what."""
    if not OCR_AVAILABLE:
        return ""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError:
        return ""


def analyze_screenshot_offline(image_bytes: bytes) -> dict:
    """
    Fallback path used when Gemini/internet is unavailable: local OCR + heuristic
    scoring only. Limitation: plain OCR can't separate the two sides of a chat,
    so this analyzes ALL visible text, not just the other person's message.
    """
    if not OCR_AVAILABLE:
        return {
            "mock": False,
            "source": "offline_fallback",
            "error": "OCR not installed (pip install pytesseract pillow, plus the Tesseract engine itself)",
            "extracted_text": "",
            "ai_likelihood": 50,
            "reasoning": [],
            "confidence": "low",
            "chat_sides_detected": "ocr_mixed",
        }

    extracted_text = extract_text_from_image(image_bytes)

    if not extracted_text:
        return {
            "mock": False,
            "source": "offline_fallback",
            "extracted_text": "",
            "ai_likelihood": 50,
            "reasoning": ["OCR could not read any text from this image."],
            "confidence": "low",
            "chat_sides_detected": "ocr_mixed",
        }

    result = analyze_text(extracted_text)
    reasoning = [f"Pattern check: {r}" for r in result.get("reasoning", [])]
    reasoning.append("Offline mode: could not separate the two sides of the chat - this reflects ALL visible text")

    return {
        "mock": False,
        "source": "offline_fallback",
        "extracted_text": extracted_text,
        "ai_likelihood": result.get("heuristic_score", 50),
        "heuristic_score": result.get("heuristic_score", 50),
        "heuristic_breakdown": result.get("breakdown", {}),
        "reasoning": reasoning,
        "confidence": "low",
        "chat_sides_detected": "ocr_mixed",
    }