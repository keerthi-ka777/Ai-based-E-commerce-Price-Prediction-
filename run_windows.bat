@echo off
echo ==============================================
echo AI E-Commerce Price Prediction - Setup
echo ==============================================
py -3.13 -m venv venv
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist models\price_model.joblib (
    python scripts\train_model.py
)
python app.py
pause
