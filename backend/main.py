# backend/main.py
import os, asyncio, base64
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi.responses import JSONResponse

from supabase import create_client
from backend.intent import extract_intent
from backend.browser import launch_and_capture
import threading
import time

load_dotenv()
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SUPA_URL = os.getenv("SUPABASE_URL")
SUPA_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPA_URL, SUPA_KEY)

@app.websocket("/ws")
async def websocket_handler(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"msg": "connected"})
    try:
        while True:
            data = await ws.receive_json()
            transcript = data.get("speech")
            if not transcript:
                continue

            # Intent extraction via Gemini LLM
            intent_url = await extract_intent(transcript)
            # Log interaction
            await supabase.table("interactions").insert({
                "transcript": transcript,
                "intent": intent_url
            }).execute()

            await ws.send_json({"type": "intent", "intent": intent_url})
            # Launch browser, navigate, and return screenshot
            img = await launch_and_capture(intent_url)
            await ws.send_json({"type": "screenshot", "image": base64.b64encode(img).decode()})
    except Exception as e:
        await ws.send_json({"type": "error", "error": str(e)})

# --- New REST endpoint for direct Playwright command execution ---
from fastapi import Body

@app.post("/run_command")
async def run_command(payload: dict = Body(...)):
    command = payload.get("command")
    if not command:
        return JSONResponse({"error": "No command provided."}, status_code=400)
    # For now, treat command as a URL
    try:
        img = await launch_and_capture(command)
        img_b64 = base64.b64encode(img).decode()
        return {"screenshot": img_b64}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# --- New WebSocket endpoint for live browser streaming ---
@app.websocket("/ws/live")
async def live_browser(ws: WebSocket):
    await ws.accept()
    url = await ws.receive_text()  # Receive URL to open
    from backend.browser import launch_and_capture
    from playwright.async_api import async_playwright
    import asyncio
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        try:
            while True:
                img_bytes = await page.screenshot(type="png")
                img_b64 = base64.b64encode(img_bytes).decode()
                await ws.send_text(img_b64)
                await asyncio.sleep(0.5)  # 500ms
        except Exception as e:
            await ws.close()
        finally:
            await browser.close()

# --- Live browser session state ---
live_browser_state = {
    "thread": None,
    "stop": False,
    "screenshot_path": "backend/latest_screenshot.png",
    "url": None,
}

def live_browser_worker(url, screenshot_path, state):
    import asyncio
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        while not state["stop"]:
            page.screenshot(path=screenshot_path, type="png", full_page=True)
            time.sleep(0.5)
        browser.close()

@app.post("/start_live_browser")
def start_live_browser(payload: dict = Body(...)):
    url = payload.get("url")
    if not url:
        return JSONResponse({"error": "No URL provided."}, status_code=400)
    # Stop any previous session
    if live_browser_state["thread"] and live_browser_state["thread"].is_alive():
        live_browser_state["stop"] = True
        time.sleep(1)
    live_browser_state["stop"] = False
    live_browser_state["url"] = url
    t = threading.Thread(target=live_browser_worker, args=(url, live_browser_state["screenshot_path"], live_browser_state), daemon=True)
    live_browser_state["thread"] = t
    t.start()
    return {"status": "started"}

@app.post("/stop_live_browser")
def stop_live_browser():
    live_browser_state["stop"] = True
    return {"status": "stopped"}

@app.get("/live_screenshot")
def live_screenshot():
    path = live_browser_state["screenshot_path"]
    if not os.path.exists(path):
        return JSONResponse({"error": "No screenshot available."}, status_code=404)
    with open(path, "rb") as f:
        img_bytes = f.read()
    img_b64 = base64.b64encode(img_bytes).decode()
    return {"screenshot": img_b64}
