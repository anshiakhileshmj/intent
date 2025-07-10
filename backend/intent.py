# backend/intent.py
import os, httpx
from dotenv import load_dotenv

load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_KEY") or "AIzaSyAsnVKLpr5M4h9QOsQ6FF_GG7tRzLpV2cc"  # fallback for testing

async def extract_intent(text: str) -> str:
    if not GEMINI_KEY or GEMINI_KEY.startswith("your-"):
        raise RuntimeError("Gemini API key is missing or invalid. Set GEMINI_KEY in your .env file.")
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
    prompt = f"User said: \"{text}\". Extract a single valid URL to navigate to. If none, search Google and return best result's URL."
    payload = {"contents":[{"parts":[{"text": prompt}]}]}
    headers = {"Authorization": f"Bearer {GEMINI_KEY}"}
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload)
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Gemini API error: {e.response.status_code} {e.response.text}")
    content = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    return content
