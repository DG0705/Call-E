import pyttsx3

engine = pyttsx3.init()
engine.setProperty('rate', 160)

def speak(text):
    print("AI:", text)
    engine.say(text)
    engine.runAndWait()