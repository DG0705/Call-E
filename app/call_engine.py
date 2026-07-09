import asyncio
import os
import uuid
import sounddevice as sd
from scipy.io.wavfile import write
import pygame  # <-- NEW: For non-blocking audio playback

# Local imports
from .stt import transcribe_audio
from .sentiment import analyze_sentiment
from .llm import async_generate_llm_response 
from .tts import text_to_speech  # <-- NEW: Importing your edge-tts module

# Ensure recordings directory exists
RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Initialize pygame mixer for audio playback
pygame.mixer.init()

async def async_play_audio(file_path: str):
    """Plays audio without blocking the FastAPI async event loop."""
    loop = asyncio.get_running_loop()
    
    def play():
        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as e:
            print(f"Audio playback error: {e}")
            
    await loop.run_in_executor(None, play)

async def async_record_audio(duration=5) -> str:
    """Simulates inbound audio recording."""
    fs = 44100
    print("\n[🎙️ AI is Listening... Speak now!]")
    
    loop = asyncio.get_running_loop()
    recording = await loop.run_in_executor(
        None, 
        lambda: sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32', device=None)
    )
    await loop.run_in_executor(None, sd.wait)

    filename = f"{uuid.uuid4()}.wav"
    filepath = os.path.join(RECORDINGS_DIR, filename)
    write(filepath, fs, recording)
    return filepath

async def run_support_call(customer_name: str = "Customer"):
    call_active = True
    turn_count = 0
    max_turns = 4
    frustration_strikes = 0
    conversation_history = []
    
    intro_text = f"Hello {customer_name}, this is Call-E Support. How can I help you today?"
    print(f"\n[🤖 Call-E]: {intro_text}")
    
    # Execute Async TTS for the intro
    intro_audio_path = os.path.join(RECORDINGS_DIR, f"sys_intro_{uuid.uuid4()}.mp3")
    tts_success = await text_to_speech(intro_text, intro_audio_path)
    if tts_success:
        await async_play_audio(intro_audio_path)

    while call_active and turn_count < max_turns:
        turn_count += 1
        
        # A. Listen
        audio_in_path = await async_record_audio(duration=5)
        
        # B. Transcribe locally
        user_text = await transcribe_audio(audio_in_path)
        print(f"[👤 Customer]: {user_text}")
        
        if not user_text.strip():
            continue

        # C. Sentiment Check
        sentiment = analyze_sentiment(user_text)
        if sentiment == "Negative":
            frustration_strikes += 1
            print(f"[⚠️ System]: Negative sentiment detected. Strike {frustration_strikes}/2")
        
        if frustration_strikes >= 2 or "human" in user_text.lower() or "agent" in user_text.lower():
            escalation_msg = "I realize this is frustrating. Let me transfer you directly to a human support agent."
            print(f"[🤖 Call-E ESCALATING]: {escalation_msg}")
            
            esc_audio_path = os.path.join(RECORDINGS_DIR, f"sys_esc_{uuid.uuid4()}.mp3")
            if await text_to_speech(escalation_msg, esc_audio_path):
                await async_play_audio(esc_audio_path)
                
            conversation_history.append({"role": "user", "text": user_text})
            conversation_history.append({"role": "system", "action": "ESCALATED_TO_HUMAN"})
            break

        # D. Respond via Groq Cloud LLM
        bot_response = await async_generate_llm_response(user_text, conversation_history)
        print(f"[🤖 Call-E]: {bot_response}")
        
        # E. Speak the LLM response asynchronously
        reply_audio_path = os.path.join(RECORDINGS_DIR, f"sys_reply_{uuid.uuid4()}.mp3")
        if await text_to_speech(bot_response, reply_audio_path):
            await async_play_audio(reply_audio_path)
        
        # F. Update the history array
        conversation_history.append({"role": "user", "text": user_text})
        conversation_history.append({"role": "bot", "text": bot_response})
        
        if "transferring" in bot_response.lower() or "transfer" in bot_response.lower():
            call_active = False

    print("\n[📞 Call Ended]")
    return {
        "status": "Escalated" if frustration_strikes >= 2 else "Resolved",
        "final_sentiment": "Negative" if frustration_strikes > 0 else "Neutral",
        "turns": turn_count,
        "history": conversation_history
    }