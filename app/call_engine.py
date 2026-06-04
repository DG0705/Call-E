import asyncio
import os
import uuid
import sounddevice as sd
from scipy.io.wavfile import write
import pyttsx3

# Local imports
from .stt import transcribe_audio
from .sentiment import analyze_sentiment

# Ensure recordings directory exists
RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Initialize offline TTS (Windows Safe)
tts_engine = pyttsx3.init()
tts_engine.setProperty('rate', 160)

def text_to_speech(text: str):
    """Offline Text-to-Speech using pyttsx3. 
    Kept synchronous on Windows to prevent COM thread freezing."""
    tts_engine.say(text)
    tts_engine.runAndWait()

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

def generate_keyword_response(user_text: str) -> str:
    """Zero-RAM Intelligent Keyword Router"""
    text = user_text.lower()
    
    if "refund" in text or "money" in text:
        return "I can help with a refund. Could you provide your order number?"
    elif "password" in text or "login" in text:
        return "I can send a password reset link to your phone. Should I do that now?"
    elif "human" in text or "agent" in text:
        return "Transferring you to a human agent now. Please hold."
    elif len(text) < 3 or text == "you" or text == "thank you":
        return "I didn't quite catch that. Could you repeat?"
    
    return "I want to make sure I resolve this. Could you provide a bit more detail?"

async def run_support_call(customer_name: str = "Customer"):
    call_active = True
    turn_count = 0
    max_turns = 4
    frustration_strikes = 0
    conversation_history = []
    
    intro_text = f"Hello {customer_name}, this is Call-E Support. How can I help you today?"
    print(f"\n[🤖 Call-E]: {intro_text}")
    
    # Run synchronously to prevent Windows thread freeze
    text_to_speech(intro_text)

    while call_active and turn_count < max_turns:
        turn_count += 1
        
        # A. Listen
        audio_in_path = await async_record_audio(duration=5)
        
        # B. Transcribe
        user_text = await transcribe_audio(audio_in_path)
        print(f"[👤 Customer]: {user_text}")
        
        if not user_text.strip():
            continue
            
        conversation_history.append({"role": "user", "text": user_text})

        # C. Sentiment Check
        sentiment = analyze_sentiment(user_text)
        if sentiment == "Negative":
            frustration_strikes += 1
            print(f"[⚠️ System]: Negative sentiment detected. Strike {frustration_strikes}/2")
        
        if frustration_strikes >= 2 or "human" in user_text.lower():
            escalation_msg = "I realize this is frustrating. Let me transfer you directly to a human support agent."
            print(f"[🤖 Call-E ESCALATING]: {escalation_msg}")
            text_to_speech(escalation_msg)
            conversation_history.append({"role": "system", "action": "ESCALATED_TO_HUMAN"})
            break

        # D. Respond
        bot_response = generate_keyword_response(user_text)
        print(f"[🤖 Call-E]: {bot_response}")
        text_to_speech(bot_response)
        conversation_history.append({"role": "bot", "text": bot_response})
        
        if "transferring" in bot_response.lower():
            call_active = False

    print("\n[📞 Call Ended]")
    return {
        "status": "Escalated" if frustration_strikes >= 2 else "Resolved",
        "final_sentiment": "Negative" if frustration_strikes > 0 else "Neutral",
        "turns": turn_count,
        "history": conversation_history
    }