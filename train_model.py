import sys
from pathlib import Path
import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import MODEL_PATH, MODEL_DIR
from ml_model import FEATURES

rng = np.random.default_rng(42)
n = 3000

base = rng.uniform(199, 15000, n)
competitor = base * rng.uniform(0.75, 1.15, n)
discount = rng.uniform(0, 60, n)
rating = rng.uniform(2.5, 5.0, n)
demand = rng.uniform(5, 100, n)
popularity = rng.uniform(5, 100, n)
trend = rng.uniform(0, 100, n)
return_risk = rng.uniform(0, 100, n)
weather = rng.uniform(0, 1, n)
loyalty = rng.uniform(0, 100, n)
lifecycle = rng.uniform(0, 100, n)

# Synthetic historical-style target. The Random Forest learns this non-linear
# relationship; it is deliberately noisy to resemble imperfect business data.
target = (
    base * (1 - discount / 220)
    + (competitor - base) * 0.28
    + demand * base / 1200
    + popularity * base / 2500
    + trend * base / 3000
    + weather * base * 0.08
    - return_risk * base / 3500
    + loyalty * base / 5000
    + lifecycle * base / 6000
    + (rating - 3.5) * base * 0.025
    + rng.normal(0, base * 0.035)
)
target = np.clip(target, 99, None)

X = np.column_stack([
    base, competitor, discount, rating, demand, popularity,
    trend, return_risk, weather, loyalty, lifecycle
])

model = RandomForestRegressor(
    n_estimators=220,
    max_depth=14,
    min_samples_leaf=2,
    random_state=42,
    n_jobs=-1,
)
model.fit(X, target)

MODEL_DIR.mkdir(exist_ok=True)
joblib.dump(model, MODEL_PATH)
print(f"Random Forest model trained with {n} rows.")
print(f"Saved to: {MODEL_PATH}")
