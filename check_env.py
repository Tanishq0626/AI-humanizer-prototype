import os
from dotenv import load_dotenv
from google import genai

load_dotenv(encoding="utf-8-sig")
key = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=key)

try:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Say hello in one word."
    )
    print("SUCCESS:", response.text)
except Exception as e:
    print("FAILURE:", type(e).__name__, "-", str(e))