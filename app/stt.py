import sounddevice as sd
from scipy.io.wavfile import write
import whisper
import uuid
import os

model = None

def get_model():
    global model
    if model is None:
        print("Loading Whisper model...")
        model = whisper.load_model("base")
    return model

RECORDINGS_DIR = "recordings"


def record_audio(duration=5):
    fs = 44100

    print("=== Recording Started ===")

    device_index = 9  # <-- IMPORTANT (your mic)

    recording = sd.rec(
        int(duration * fs),
        samplerate=fs,
        channels=1,
        dtype='float32',
        device=device_index
    )

    sd.wait()

    print("=== Recording Finished ===")

    filename = f"{uuid.uuid4()}.wav"
    filepath = os.path.join(RECORDINGS_DIR, filename)

    write(filepath, fs, recording)

    print("Saved:", filepath)

    return filepath


def transcribe_audio(filepath):
    print("Transcribing...")
    model = get_model()
    result = model.transcribe(filepath)
    text = result["text"]
    print("Customer:", text)
    return text