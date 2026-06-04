import os
import edge_tts

# Default high-quality, clear neural voice for Indian English support contexts
DEFAULT_VOICE = "en-IN-NeerjaNeural"

async def text_to_speech(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> bool:
    """
    Asynchronously generates a natural audio response from text.
    Outputs directly to the specified file path for call routing streams.
    """
    if not text:
        return False

    try:
        # Clean up any residual old audio file at that location
        if os.path.exists(output_path):
            os.remove(output_path)

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        
        # Verify the file was written and has contents
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        return False

    except Exception as e:
        print(f"TTS Synthesis error using edge-tts: {e}")
        return False