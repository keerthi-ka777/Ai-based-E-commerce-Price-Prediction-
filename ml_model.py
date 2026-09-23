from pathlib import Path
import joblib
import numpy as np
from config import MODEL_PATH

FEATURES = [
    "base_price",
    "competitor_price",
    "discount",
    "rating",
    "demand_score",
    "popularity_index",
    "social_trend",
    "return_risk",
    "weather_impact",
    "loyalty_score",
    "lifecycle_score",
]

def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "Random Forest model not found. Run: python scripts/train_model.py"
        )
    return joblib.load(MODEL_PATH)

def predict_price(features: dict) -> float:
    model = load_model()
    row = np.array([[float(features[name]) for name in FEATURES]], dtype=float)
    prediction = float(model.predict(row)[0])
    return max(1.0, round(prediction, 2))
