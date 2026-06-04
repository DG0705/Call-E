import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from faster_whisper import WhisperModel

# Initialize the model out-of-band so it loads into memory only once
# Uses 'cuda' if an NVIDIA GPU is present, otherwise falls back to 'cpu'
# 'int8' quantization slashes RAM usage while keeping execution fast
try:
    MODEL_SIZE = "base"
    print(f"Initializing local Speech-to-Text engine ({MODEL_SIZE})...")
    stt_model = WhisperModel(MODEL_SIZE, device="auto", compute_type="int8")
    print("STT Engine initialized successfully.")
except Exception as e:
    print(f"Error initializing local STT model: {e}")
    stt_model = None

# Thread pool execution to prevent blocking FastAPI's main async event loop
executor = ThreadPoolExecutor(max_workers=4)

def _sync_transcribe(audio_path: str) -> str:
    """Synchronous core execution for faster-whisper."""
    if not stt_model:
        return "[STT Error: Model not loaded]"
    
    if not os.path.exists(audio_path):
        return ""

    segments, info = stt_model.transcribe(audio_path, beam_size=5)
    text_segments = [segment.text for segment in segments]
    return " ".join(text_segments).strip()

async def transcribe_audio(audio_path: str) -> str:
    """
    Asynchronously transcribes a local audio file (.wav/.mp3).
    Integrates directly with call_engine.py processing pipelines.
    """
    loop = asyncio.get_running_loop()
    try:
        text = await loop.run_in_executor(executor, _sync_transcribe, audio_path)
        return text
    except Exception as e:
        print(f"Transcription execution error: {e}")
        return ""