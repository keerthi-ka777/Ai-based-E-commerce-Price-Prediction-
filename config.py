from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "ecommerce.db"

MODEL_PATH = MODEL_DIR / "price_model.joblib"

MODEL_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# Bengaluru defaults for the demo. Users can change these from the UI.
DEFAULT_LAT = 12.9716
DEFAULT_LON = 77.5946
