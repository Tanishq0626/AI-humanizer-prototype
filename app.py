from flask import Flask, render_template, request, jsonify
from gemini_service import analyze_screenshot, analyze_text_message
from human_ai_scorer import analyze_text, analyze_screenshot_offline
import traceback

app = Flask(__name__)


def weighted_combine(gemini_score, heuristic_score, confidence):
    """Blend Gemini's score with the local heuristic score, trusting Gemini
    more heavily when it reports high confidence in its own verdict, and
    leaning on the heuristic more only when Gemini itself is unsure."""
    if confidence == "high":
        gemini_weight = 0.97
    elif confidence == "low":
        gemini_weight = 0.85
    else:
        gemini_weight = 0.92
    return round(gemini_weight * gemini_score + (1 - gemini_weight) * heuristic_score)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/analyze-text', methods=['POST'])
def analyze_text_route():
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "No text provided"}), 400

        gemini_result = analyze_text_message(text)
        heuristic_result = analyze_text(text)

        # If Gemini fails, we still have the heuristic score - no OCR needed
        # since the user already gave us clean text directly.
        if gemini_result.get("error"):
            print(f"[GEMINI ERROR] {gemini_result['error']}")
            return jsonify({
                "mock": False,
                "source": "heuristic_only",
                "extracted_text": text,
                "ai_likelihood": heuristic_result.get("heuristic_score", 50),
                "heuristic_score": heuristic_result.get("heuristic_score", 50),
                "heuristic_breakdown": heuristic_result.get("breakdown", {}),
                "reasoning": [f"Pattern check: {r}" for r in heuristic_result.get("reasoning", [])],
                "confidence": "low",
                "chat_sides_detected": "n/a",
                "gemini_error": gemini_result["error"],
            })

        gemini_score = gemini_result.get("ai_likelihood", 50)
        heuristic_score = heuristic_result.get("heuristic_score", 50)
        confidence = gemini_result.get("confidence", "medium")
        combined_score = weighted_combine(gemini_score, heuristic_score, confidence)

        combined_reasoning = (
            [f"Gemini: {r}" for r in gemini_result.get("reasoning", [])]
            + [f"Pattern check: {r}" for r in heuristic_result.get("reasoning", [])]
        )

        return jsonify({
            "mock": False,
            "source": "combined",
            "extracted_text": text,
            "ai_likelihood": combined_score,
            "gemini_score": gemini_score,
            "heuristic_score": heuristic_score,
            "heuristic_breakdown": heuristic_result.get("breakdown", {}),
            "reasoning": combined_reasoning,
            "confidence": confidence,
            "chat_sides_detected": "n/a",
        })

    except Exception as e:
        print("[UNHANDLED ERROR IN /analyze-text]")
        traceback.print_exc()
        return jsonify({
            "error": f"Server error: {str(e)}",
            "ai_likelihood": 50,
            "extracted_text": "",
            "reasoning": ["An unexpected server error occurred. Check the terminal for details."],
            "confidence": "low",
            "chat_sides_detected": "unclear",
        }), 500


@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        if 'screenshot' not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files['screenshot']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        image_bytes = file.read()
        mime_type = file.mimetype or "image/png"

        gemini_result = analyze_screenshot(image_bytes, mime_type)

        # If Gemini failed (no internet, API down, etc.) fall back to local OCR + heuristic
        if gemini_result.get("error"):
            print(f"[GEMINI ERROR] {gemini_result['error']}")
            offline_result = analyze_screenshot_offline(image_bytes)
            offline_result["gemini_error"] = gemini_result["error"]
            return jsonify(offline_result)

        extracted_text = gemini_result.get("extracted_text", "")
        heuristic_result = analyze_text(extracted_text)

        gemini_score = gemini_result.get("ai_likelihood", 50)
        heuristic_score = heuristic_result.get("heuristic_score", 50)
        confidence = gemini_result.get("confidence", "medium")
        combined_score = weighted_combine(gemini_score, heuristic_score, confidence)

        # Label each reasoning line by source so judges can see exactly where it came from
        combined_reasoning = (
            [f"Gemini: {r}" for r in gemini_result.get("reasoning", [])]
            + [f"Pattern check: {r}" for r in heuristic_result.get("reasoning", [])]
        )

        return jsonify({
            "mock": False,
            "source": "combined",
            "extracted_text": extracted_text,
            "ai_likelihood": combined_score,
            "gemini_score": gemini_score,
            "heuristic_score": heuristic_score,
            "heuristic_breakdown": heuristic_result.get("breakdown", {}),
            "reasoning": combined_reasoning,
            "confidence": confidence,
            "chat_sides_detected": gemini_result.get("chat_sides_detected", "unclear"),
        })

    except Exception as e:
        print("[UNHANDLED ERROR IN /upload]")
        traceback.print_exc()
        return jsonify({
            "error": f"Server error: {str(e)}",
            "ai_likelihood": 50,
            "extracted_text": "",
            "reasoning": ["An unexpected server error occurred. Check the terminal for details."],
            "confidence": "low",
            "chat_sides_detected": "unclear",
        }), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)