import os
from faster_whisper import WhisperModel
from gtts import gTTS

# ==========================================
# 1. SPEECH TO TEXT (STT) via Faster-Whisper
# ==========================================
def speech_to_text(audio_file_path, model_size="base"):
    """
    Transcribes an audio file into text using faster-whisper.
    Supported model_size options: 'tiny', 'base', 'small', 'medium', 'large-v3'
    """
    print(f"Loading Faster-Whisper model ({model_size})...")
    
    # Automatically switch to GPU (cuda) if available, otherwise fallback to CPU.
    # We use int8 quantization to save VRAM/RAM and speed up execution.
    device = "cuda" if os.system("nvidia-smi > /dev/null 2>&1") == 0 else "cpu"
    model = WhisperModel(model_size, device=device, compute_type="int8")
    
    print(f"Transcribing audio file: {audio_file_path}...")
    
    # beam_size=5 is the default sweet spot for accuracy vs speed
    segments, info = model.transcribe(audio_file_path, beam_size=5)
    
    print(f"Detected language: '{info.language}' with probability {info.language_probability:.2f}\n")
    
    # Collect transcription chunks
    full_transcript = []
    for segment in segments:
        print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
        full_transcript.append(segment.text)
        
    return "".join(full_transcript)


# ==========================================
# 2. TEXT TO SPEECH (TTS) via gTTS
# ==========================================
def text_to_speech(text, output_audio_path, lang="en"):
    """
    Converts a string of text into an MP3 audio file.
    """
    print(f"\nConverting text to speech...")
    
    # Initialize the TTS object
    tts = gTTS(text=text, lang=lang, slow=False)
    
    # Save the generated speech to an audio file
    tts.save(output_audio_path)
    print(f"Audio successfully saved to: {output_audio_path}")


# ==========================================
# EXECUTION PIPELINE
# ==========================================
if __name__ == "__main__":
    # Define your paths
    sample_input_audio = r"C:\Users\ASHOKA-PC\Downloads\Recording.mp3"  # Replace with a real audio path to test STT
    sample_output_audio = r"C:\Users\ASHOKA-PC\Downloads\output_speech.mp3"
    
    # --- Example 1: Run Speech-to-Text ---
    # Create a dummy file check so the script doesn't crash if you don't have an audio file ready
    if os.path.exists(sample_input_audio):
        extracted_text = speech_to_text(sample_input_audio, model_size="base")
        print(f"\nFinal Transcribed Text:\n{extracted_text}")
    else:
        print(f"Input file '{sample_input_audio}' not found. Skipping STT demo.")
        extracted_text = "Hello developer! This is an example text synthesized into an audio file."

    # --- Example 2: Run Text-to-Speech ---
    text_to_speech(extracted_text, sample_output_audio, lang="en")