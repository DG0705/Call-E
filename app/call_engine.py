import re
from .tts import speak
from .stt import record_audio, transcribe_audio


def extract_rating(text):
    if not text:
        return "Not Given"

    numbers = re.findall(r'\d', text)

    if numbers and numbers[0] in ["1", "2", "3", "4", "5"]:
        return numbers[0]

    return "Not Given"


def ask_question(question):
    speak(question)
    audio_path = record_audio(duration=6)
    text = transcribe_audio(audio_path)
    return text, audio_path


def start_call():
    try:
        speak("Hello, this is Call-e Enterprise calling for your feedback.")

        rating_text, rating_audio = ask_question(
            "On a scale of 1 to 5, how would you rate our service?"
        )
        rating = extract_rating(rating_text)

        recommendation, rec_audio = ask_question(
            "Would you recommend us to others?"
        )

        suggestion, sug_audio = ask_question(
            "Do you have any suggestions for improvement?"
        )

        speak("Thank you for your valuable feedback. Goodbye.")

        return {
            "rating": rating,
            "recommendation": recommendation,
            "suggestion": suggestion,
            "recording_path": sug_audio  # store last recording
        }

    except Exception as e:
        print("Call Engine Error:", e)
        return {
            "rating": "Error",
            "recommendation": "Error",
            "suggestion": "Error",
            "recording_path": None
        }