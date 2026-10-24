# Signal — AI Chat Analyzer

> Upload a chat screenshot or paste a message, and get an **estimated** probability that it was written by an AI, with reasons.
> Built in 24 hours at **Grand Hack IPEC** (HackShastra). **Status: archived. I've deliberately stopped developing it. See [Why I stopped](#why-i-stopped).**

---

## Overview

Signal answers one question: *"Does this message sound like a human wrote it, or an AI?"*

You give it either:

- a **screenshot** of a chat (WhatsApp, Instagram, Gmail, a dating app, customer support), or
- **pasted text**.

It returns:

- the **extracted text** (for screenshots),
- an **AI-likelihood %** and a **human-likeness %**,
- a **plain-English reasoning log** that shows which signals pushed the score up or down.

Results are always framed as an **estimate, never proof**. That was a deliberate decision, not a disclaimer added later (see [Honest limitations](#honest-limitations)).

---

## How it works

```
 ┌────────────┐
 │  Frontend  │  screenshot (drag/drop/paste)  OR  pasted text
 └─────┬──────┘
       ▼
 ┌────────────┐
 │   Flask    │  /upload (image)      /analyze-text (JSON)
 └─────┬──────┘
       ▼
 ┌─────────────────────┐     ┌──────────────────────────────┐
 │  Gemini API         │     │  Local heuristic scorer      │
 │  • reads the image  │     │  (pure Python, no network)   │
 │    (OCR)            │     │  • sentence-length uniformity│
 │  • judges the text  │     │  • contractions              │
 │  • returns score,   │     │  • punctuation consistency   │
 │    reasoning,       │     │  • generic "assistant" phrases│
 │    confidence       │     └──────────────┬───────────────┘
 └─────────┬───────────┘                    │
           └───────────────┬────────────────┘
                           ▼
              Confidence-weighted blend (Flask)
                           ▼
        Frontend: extracted text · final % · reasoning
```

### Scoring: confidence-weighted blend

```
final_score = gemini_weight × gemini_score + (1 − gemini_weight) × heuristic_score
```

| Gemini's self-reported confidence | `gemini_weight` |
|---|---|
| high | 0.97 |
| medium (default) | 0.92 |
| low | 0.85 |

Why the blend is lopsided: testing showed my own heuristic signals don't reliably catch modern AI writing (see below). So Gemini carries most of the weight, and the heuristic acts as a transparent second opinion.

### Determinism

Same input should give the same output. Gemini is called with `temperature=0, top_p=1, top_k=1`, and the blend is plain arithmetic.

### Offline fallback

- If Gemini is unreachable or errors, the app falls back to **heuristic-only** scoring.
- For screenshots in offline mode, it tries local OCR via `pytesseract`. This needs Tesseract installed separately, and fails gracefully (empty text, no crash) if it's missing.

### About the OCR

Screenshot text is read by **Gemini's built-in vision**, not an OCR engine I built. Building and training a reliable OCR for chat screenshots (dark mode, bubbles, emojis, Hinglish) isn't realistic in 24 hours, and a hand-rolled one wouldn't beat what's already available. Using Gemini for this was a deliberate scoping decision.

---

## What I built vs. what I used

| Built by us | Used off the shelf |
|---|---|
| Frontend (dark/light UI, dropzone, text box, results view) | Gemini API (OCR + text judgment) |
| Flask backend and routes, JSON error handling | Flask, `google-genai`, `python-dotenv` |
| Prompt design and calibration for Gemini | `pytesseract` (offline OCR fallback) |
| Local heuristic scorer (4 signals) | |
| Confidence-weighted blending and fallbacks | |

To be upfront: the core intelligence, the OCR and the "is this AI?" judgment, comes from a third-party API. What's mine is the pipeline, the calibration, the fallbacks and the interface around it.

---

## Project structure

```
AI-Chat-Analyzer/
├── app.py               # Flask app: "/", "/upload", "/analyze-text"; blending + fallbacks
├── gemini_service.py    # Gemini calls: analyze_screenshot(), analyze_text_message()
├── human_ai_scorer.py   # Heuristic scorer + offline OCR fallback
├── templates/
│   └── index.html       # Frontend
├── .env.example         # Template for your API key
├── .gitignore
└── README.md
```

| File | Responsibility |
|---|---|
| `app.py` | Routes, combines Gemini and heuristic scores via `weighted_combine()`, wraps routes in try/except so errors come back as JSON, not HTML |
| `gemini_service.py` | Model name, deterministic generation config, calibrated prompts for image and text paths |
| `human_ai_scorer.py` | Sentence uniformity, contractions, punctuation, generic phrasing → 0–100 score plus breakdown |
| `templates/index.html` | Upload/paste UI, one "Analyze chat" button, percentage split bar, reasoning log |

### API

| Route | Method | Input | Output |
|---|---|---|---|
| `/` | GET | none | the web UI |
| `/upload` | POST | multipart field `screenshot` | extracted text, scores, reasoning |
| `/analyze-text` | POST | JSON `{"text": "..."}` | scores, reasoning |

---

## Run it locally

```bash
git clone <this-repo>
cd AI-Chat-Analyzer

python -m venv venv
# Windows: venv\Scripts\activate     macOS/Linux: source venv/bin/activate

pip install flask google-genai python-dotenv
pip install pytesseract pillow       # optional, offline OCR fallback (needs Tesseract installed)

cp .env.example .env                 # then put your own key in .env
python app.py                        # opens on http://127.0.0.1:5000
```

`.env`:

```
GEMINI_API_KEY=your_key_here
```

Notes:

- `.env` must be in the **project root**, next to `app.py`.
- **Never commit `.env`.** It is in `.gitignore`.
- Restart Flask fully after editing any `.py` file.
- Google retires model names often. If you get a 404, change `MODEL_NAME` in `gemini_service.py` to a model your key can list.

---

## What I tested and found

These are real results from my own testing, not marketing:

| Test | Result |
|---|---|
| AI-generated exam notes (formal, fragment-heavy) | ~56% AI. Far too low for text that was 100% AI-written. |
| AI-written emotional apology message | ~52–62% AI. Borderline despite being fully AI-generated. |
| Casual Hinglish message | Initially flagged as AI. Fixed with prompt calibration. |
| Same input, repeated | Stable after temperature 0 and the confidence-weighted blend. |
| Same screenshot vs. GPTZero / ZeroGPT / Copyleaks | Scores diverged. Mine leaned "human" where they leaned "AI". |

What I learned from this:

1. **My heuristic signals don't generalize.** Contractions, punctuation and sentence-length variation were designed around casual chat. Formal text, Hinglish and modern LLM output (which uses contractions and varies sentence length) break them.
2. **A well-calibrated 90%+ is hard to reach on short chat messages.** There simply isn't much signal in two lines of text.
3. **The score is only as good as the model behind it.** Most of the final number is Gemini's judgment, so I can't honestly claim the result comes from my own algorithm.

---

## Honest limitations

- AI-text detection is **unreliable in general**, not just in this project. Even OpenAI shut down its own AI-text classifier in 2023 because of its low accuracy. Any detector, including this one, produces false positives and false negatives.
- Short messages carry very little signal.
- The heuristic layer is weak on formal text, non-English or mixed-language text (e.g. Hinglish), and polished AI writing.
- Screenshots: when OCR falls back to local mode it can't separate the two sides of a chat. Gemini mode can.
- No persistent storage. Nothing is saved between requests.
- Requires an internet connection and a Gemini API key for the good results.
- Don't use this to accuse someone of anything. It gives an estimate, not evidence.

---

## Why I stopped

After the hackathon I seriously considered turning this into a real product, for example a browser extension with an icon in the WhatsApp Web / ChatGPT / Claude text bar. I decided not to, for these reasons:

**1. The space is crowded and the incumbents are far ahead.**
Tools like QuillBot, GPTZero, ZeroGPT and Copyleaks have been doing AI detection and text rewriting for years, with large teams, their own trained models, huge datasets and established user bases. Their detectors are better than mine, and in side-by-side tests my scores disagreed with theirs. Chat apps are also adding built-in writing help. A solo student project can't out-build that.

**2. I'm a thin layer over someone else's model.**
The two things that matter most, reading the screenshot and judging whether text is AI, are done by the Gemini API. My own scoring logic is the weakest part. A product that is mostly an API wrapper has no moat: anyone can call the same API.

**3. The "detect AI" problem has a ceiling.**
Because detection on short chat messages is inherently unreliable, even a much better version of this would still produce results people can't fully trust. Building a business or a reputation on a score that can't be defended isn't something I want to do.

**4. The problem is real, but it's not mine to win.**
People genuinely want to know whether they're talking to a human, and AI tools genuinely forget long conversations. But the best response to a crowded space is to pick a different problem, not to build a worse copy.

So I'm archiving this as a **portfolio project and a learning record**, not continuing it as a product.

---

## Why it was still worth building

- **A full end-to-end pipeline in 24 hours:** screenshot → vision model → scoring → blended result → UI, with fallbacks at each stage.
- **Real engineering problems solved:** model deprecation (404s), Windows BOM in `.env`, OCR crashes returning HTML instead of JSON, deterministic LLM output, and score calibration.
- **A defensible design principle:** show an estimate with reasons, never a verdict. Show which signals contributed. Fail gracefully when a component is missing.
- **A clear lesson about where an AI wrapper can and can't compete,** which is worth more to me than another half-finished product.

---

## Ideas I explored but did not build

- Per-contact writing baseline ("does this sound like how *this person* usually writes?"), which is a more tractable question than "is this AI?"
- Contact memory: daily → weekly → monthly summaries of a conversation, to get around context-window limits
- Reply-draft assistant using that memory
- WhatsApp Web / ChatGPT / Claude browser extension (would need the Gemini key kept on a backend, never in the extension)

If anyone wants to pick up any of these, feel free to fork.

---

## Credits

Built at **Grand Hack IPEC** (HackShastra, IPEC Ghaziabad) by a team of four. Lead developer: **Tanishq Bhatnagar**, who built the Flask backend, Gemini integration, scoring engine and integration. Teammates contributed backend support, heuristic research and prompt tuning, and UI/UX and pitch.

## License

Add a license of your choice (MIT is a common default for portfolio projects).
