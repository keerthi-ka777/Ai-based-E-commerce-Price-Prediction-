# AI-Based E-Commerce Price Prediction — Full Stack

Flask + SQLite + Random Forest + current shopping discovery + live weather.

## Run

```powershell
py -3.13 -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`.

## Current shopping data

The application no longer uses DummyJSON or Open Beauty Facts as the product/price source. Search, bundle options, best-value recommendations, stylist matches and wearable try-on choices use the configured Google Shopping provider through SerpApi. The provider can return current indexed seller/source, price, old price, delivery text, rating, reviews, image and product link.

Put your server-side key in `.env`:

```text
SERPAPI_KEY=your_key_here
```

The project does not scrape Amazon/Flipkart/Myntra in the browser and does not invent their prices or delivery promises. A single shopping provider cannot guarantee every retailer in the market; official/partner retailer feeds can be added later for deeper coverage.

## Location + weather

The browser can request the user's location. The application reverse-geocodes it to a city/state and uses that context for shopping search and Open-Meteo live weather. Location is not stored in SQLite. Weather-aware recommendations change with temperature, rain and humidity. For example, 40°C+ prioritizes air conditioners, coolers, fans, sunscreen, hydration and breathable clothing.

## Features

- Live multi-seller product search
- Current price, seller, rating, reviews and delivery text when supplied by the shopping source
- Location-aware shopping
- Weather-aware recommendations
- AI Best Value Product
- Random Forest price prediction
- Demand spike detection
- Social trend signal
- Weather pricing
- Customer loyalty impact
- Competitor benchmark
- Product lifecycle score
- Return-risk adjustment
- Live bundle optimization across contexts
- Customer emotion/sentiment analysis
- Personal stylist with live shopping matches
- Wearable-only Virtual Try-On catalog
- Prediction history in SQLite

## Important limitation

Exact doorstep delivery dates can depend on PIN code, seller stock, account/membership and retailer-specific services. The application displays delivery information only when the connected shopping feed supplies it. Photorealistic Virtual Try-On still requires a dedicated garment-transfer/vision model; the current upload flow links a live wearable product to that workflow.


## V6 changes
- Consumer-facing AI Price Prediction: live offer data automatically fills the model inputs; advanced loyalty/sale controls are optional.
- AI Recommendation now shows AI Best Value, Lowest Live Price, Highest Rated offer, offer count and current price range after every search.
- Prediction History UI removed.
- Virtual Try-On redesigned as a 3-step workflow matching the reference style: photo -> live wearable product -> generated result.
- Real image generation is wired to Google's Gemini image-generation API. Add `GEMINI_API_KEY` to `.env` in addition to `SERPAPI_KEY`.
- The app uses Gemini `gemini-3.1-flash-image` by default; this can be overridden with `GEMINI_IMAGE_MODEL`.
