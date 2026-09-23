POSITIVE = {
    "excellent", "good", "great", "fast", "love", "amazing", "happy",
    "quality", "perfect", "comfortable", "worth", "best", "nice", "quick"
}
NEGATIVE = {
    "bad", "poor", "slow", "hate", "broken", "late", "worst", "return",
    "refund", "damaged", "cheap", "uncomfortable", "problem", "disappointed"
}

def analyze_sentiment(text):
    words = {w.strip(".,!?;:").lower() for w in (text or "").split()}
    pos = len(words & POSITIVE)
    neg = len(words & NEGATIVE)
    total = max(1, pos + neg)
    score = round((pos - neg) / total, 2)

    if score > 0.15:
        label = "Positive"
    elif score < -0.15:
        label = "Negative"
    else:
        label = "Neutral"

    return {"sentiment": label, "score": score, "positive_hits": pos, "negative_hits": neg}
