from textblob import TextBlob

def analyze_sentiment(text):
    if not text:
        return "Neutral"
    
    analysis = TextBlob(text)
    score = analysis.sentiment.polarity

    if score > 0:
        return "Positive"
    elif score < 0:
        return "Negative"
    else:
        return "Neutral"