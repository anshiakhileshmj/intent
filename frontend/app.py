# frontend/app.py
import streamlit as st
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, WebRtcMode
import av
import numpy as np
import requests
import base64
import re
from google import generativeai as genai
import time

BACKEND_URL = "http://localhost:8000"  # Adjust if backend runs elsewhere
GEMINI_API_KEY = "AIzaSyAsnVKLpr5M4h9QOsQ6FF_GG7tRzLpV2cc"  # Replace with your Gemini API key

# --- Gemini LLM intent extraction ---
def get_url_from_gemini(command: str) -> str:
    genai.configure(api_key=GEMINI_API_KEY)
    prompt = (
        "Given the following user command, return the most appropriate URL to open in a browser. "
        "If the command is not about opening a web page, return 'NONE'. "
        f"Command: {command}\nURL: "
    )
    try:
        response = genai.GenerativeModel("gemini-2.5-pro").generate_content(prompt)
        url = response.text.strip().split("\n")[0]
        match = re.search(r'(https?://\S+|www\.\S+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', url)
        if match:
            url = match.group(0)
            if not url.startswith('http'):
                url = 'https://' + url
            return url
        if url.upper() == 'NONE':
            return None
        return url  # fallback
    except Exception as e:
        st.error(f"Gemini LLM error: {e}")
        return None

# --- Streamlit WebRTC Audio Recorder ---
class AudioProcessor(AudioProcessorBase):
    def __init__(self):
        self.frames = []
    def recv(self, frame: av.AudioFrame):
        self.frames.append(frame)
        return frame

def get_transcript_from_audio(frames):
    # Placeholder for speech-to-text logic
    # In production, send audio to AssemblyAI or another STT API
    return "(Speech-to-text not implemented in this demo)"

# --- UI Layout ---
col1, col2 = st.columns(2)

with col1:
    st.header("Automation Controls")
    # Microphone input
    st.subheader("🎤 Speak a command:")
    audio_ctx = webrtc_streamer(
        key="speech-to-text",
        mode=WebRtcMode.SENDRECV,
        audio_receiver_size=1024,
        media_stream_constraints={"audio": True, "video": False},
        audio_processor_factory=AudioProcessor,
        async_processing=False,
    )
    transcript = ""
    if audio_ctx and audio_ctx.state.playing:
        st.info("Recording... Speak now.")
        if audio_ctx.audio_processor and len(audio_ctx.audio_processor.frames) > 0:
            audio_data = np.concatenate([
                frame.to_ndarray().flatten() for frame in audio_ctx.audio_processor.frames
            ])
            transcript = get_transcript_from_audio(audio_ctx.audio_processor.frames)
            st.write(f"Transcript: {transcript}")
    # Text input
    st.subheader("Or type a command:")
    command = st.text_input("Enter a command (e.g., 'open article of ai on wikipedia'):")
    run_btn = st.button("Run Command")
    if 'live_polling' not in st.session_state:
        st.session_state['live_polling'] = False
    if run_btn or (transcript and transcript != "(Speech-to-text not implemented in this demo)"):
        user_command = command if run_btn else transcript
        with st.spinner("Thinking with Gemini LLM..."):
            url = get_url_from_gemini(user_command)
        if url:
            st.info(f"Gemini LLM extracted URL: {url}")
            # Start live browser session in backend
            resp = requests.post(f"{BACKEND_URL}/start_live_browser", json={"url": url})
            if resp.status_code == 200:
                st.session_state['live_polling'] = True
                st.session_state['last_url'] = url
            else:
                st.error(f"Backend error: {resp.text}")
        else:
            st.warning("Gemini LLM could not extract a valid URL from your command. Please try a different command.")
    if st.button("Stop Live View"):
        st.session_state['live_polling'] = False
        requests.post(f"{BACKEND_URL}/stop_live_browser")

with col2:
    st.header("Live Browser")
    st.write("The live browser view will appear here after you run a command.")
    img_placeholder = st.empty()
    if st.session_state.get('live_polling', False):
        for _ in range(200):  # Poll for up to 100 seconds
            resp = requests.get(f"{BACKEND_URL}/live_screenshot")
            if resp.status_code == 200:
                img_b64 = resp.json().get("screenshot")
                if img_b64:
                    img_bytes = base64.b64decode(img_b64)
                    img_placeholder.image(img_bytes, use_container_width=True)
            else:
                img_placeholder.info("Waiting for screenshot...")
            time.sleep(0.5)
            if not st.session_state.get('live_polling', False):
                break
