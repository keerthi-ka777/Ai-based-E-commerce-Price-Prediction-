from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from pathlib import Path
import math
import os
from dotenv import load_dotenv

load_dotenv()

from config import DEFAULT_LAT, DEFAULT_LON, UPLOAD_DIR
from database import init_db, add_prediction, recent_predictions, get_db
from ml_model import predict_price
from services.live_data import (
    fetch_weather, fetch_social_trend, geocode_city,
    search_google_shopping, reverse_geocode,
)
from services.pricing import lifecycle_score, demand_spike, choose_strategy, optimize_bundle, upcoming_sale_factor
from services.sentiment import analyze_sentiment
from services.recommendations import stylist_recommendations

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
init_db()


def safe_float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def live_shopping(query, location="", limit=40):
    """Single source of truth for current shopping discovery.
    No dummy/public demo catalog is used here. A configured SerpApi key is required.
    """
    result = search_google_shopping(query, location=location, limit=limit)
    return result


def normalise_shopping_item(item):
    return {
        "id": item.get("id"), "title": item.get("title", "Unknown Product"),
        "source": item.get("source", "Shopping source"),
        "source_icon": item.get("source_icon", ""),
        "price": item.get("extracted_price"), "price_text": item.get("price"),
        "old_price": item.get("extracted_old_price"), "old_price_text": item.get("old_price"),
        "delivery": item.get("delivery", ""), "rating": item.get("rating"),
        "reviews": item.get("reviews"), "thumbnail": item.get("thumbnail", ""),
        "url": item.get("url", ""), "snippet": item.get("snippet", ""),
        "multiple_sources": item.get("multiple_sources", False),
        "tag": item.get("tag", ""),
    }


def normalize_search_query(query):
    """Normalize a few common shopping typos without changing normal queries."""
    import re
    q = re.sub(r"\s+", " ", str(query or "").strip())
    words = q.split()
    replacements = {
        "cethaphil": "cetaphil",
        "cetaphil": "cetaphil",
    }
    words = [replacements.get(w.lower(), w) for w in words]
    return " ".join(words)


def exact_intent_filter(items, query):
    """Keep shopping results aligned with the user's actual search intent.

    For multi-word searches, important terms must appear in the product title.
    This prevents a related-but-different item (for example Cetaphil Baby Wash)
    from becoming the AI Best Value for a search specifically for a cleanser.
    """
    import re
    q = (query or "").lower().strip()
    stopwords = {"and", "the", "for", "with", "from", "buy", "best", "near", "under", "price", "online"}
    tokens = [t for t in re.findall(r"[a-z0-9]+", q) if len(t) >= 3 and t not in stopwords]
    if not tokens:
        return items
    filtered = []
    for item in items:
        title = str(item.get("title", "")).lower()
        if all(token in title for token in tokens):
            filtered.append(item)
    return filtered


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "AI E-Commerce Price Prediction API", "live_shopping_configured": bool(os.getenv("SERPAPI_KEY", "").strip())})


@app.get("/api/products")
def products():
    # Kept only for backward compatibility; it uses the live shopping provider only.
    q = normalize_search_query(request.args.get("q", ""))
    if not q:
        return jsonify({"source": "Live shopping provider", "live": False, "products": [], "message": "Search for a product to load current shopping data."})
    result = live_shopping(q, request.args.get("location", ""), 40)
    items = exact_intent_filter(result.get("items", []), q)
    return jsonify({"source": result.get("source"), "live": result.get("enabled", False), "products": [normalise_shopping_item(i) for i in items], "message": result.get("error", "")})


@app.get("/api/products/search")
def product_search():
    q = normalize_search_query(request.args.get("q", ""))
    location = request.args.get("location", "").strip()
    if not q:
        return jsonify({"query": q, "shopping": [], "shopping_enabled": False, "sources": []})
    try:
        shopping = live_shopping(q, location=location, limit=40)
    except Exception as exc:
        shopping = {"enabled": bool(os.getenv("SERPAPI_KEY", "").strip()), "items": [], "error": str(exc), "source": "Google Shopping via SerpApi"}
    items = exact_intent_filter(shopping.get("items", []), q)
    return jsonify({
        "query": q,
        "original_query": request.args.get("q", "").strip(),
        "shopping": [normalise_shopping_item(i) for i in items],
        "shopping_enabled": shopping.get("enabled", False),
        "shopping_source": shopping.get("source", ""),
        "shopping_query": shopping.get("query", q),
        "shopping_location": shopping.get("location", location),
        "shopping_error": shopping.get("error", ""),
        "sources": [shopping.get("source")] if shopping.get("enabled") else [],
    })


@app.get("/api/categories")
def categories():
    return jsonify({"categories": [
        "Beauty & Personal Care", "Fashion", "Electronics", "Home & Kitchen",
        "Grocery", "Sports & Fitness", "Shoes", "Bags & Accessories", "Appliances", "Travel"
    ]})


@app.get("/api/weather")
def weather():
    lat = safe_float(request.args.get("lat"), DEFAULT_LAT)
    lon = safe_float(request.args.get("lon"), DEFAULT_LON)
    try:
        data = fetch_weather(lat, lon)
        return jsonify({"source": "Open-Meteo live weather", "live": True, "latitude": lat, "longitude": lon, "current": data.get("current", {}), "timezone": data.get("timezone")})
    except Exception as exc:
        return jsonify({"source": "Open-Meteo", "live": False, "latitude": lat, "longitude": lon, "current": {}, "message": f"Live weather unavailable: {exc}"}), 503


@app.get("/api/geocode")
def geocode():
    q = request.args.get("q", "Bengaluru").strip()
    try:
        # Nominatim handles Indian PIN codes/localities; Open-Meteo is retained
        # as a fallback for ordinary city names.
        results = search_location(q)
        if not results:
            results = geocode_city(q)
        return jsonify({"results": results})
    except Exception as exc:
        try:
            return jsonify({"results": geocode_city(q), "error": str(exc)})
        except Exception:
            return jsonify({"results": [], "error": str(exc)}), 503


@app.get("/api/location/reverse")
def location_reverse():
    lat = safe_float(request.args.get("lat"), DEFAULT_LAT)
    lon = safe_float(request.args.get("lon"), DEFAULT_LON)
    try:
        place = reverse_geocode(lat, lon)
        return jsonify({"latitude": lat, "longitude": lon, "place": place})
    except Exception as exc:
        return jsonify({"latitude": lat, "longitude": lon, "place": {}, "error": str(exc)}), 503


def weather_context(temp, rain, humidity):
    if temp >= 40:
        return (["air conditioner", "air cooler", "ceiling fan", "sunscreen", "water bottle", "cotton clothing"], "Extreme heat detected", "Cooling, sun protection, hydration and breathable products are prioritized because the current temperature is 40°C or above.")
    if temp >= 35:
        return (["air cooler", "fan", "sunscreen", "cotton clothing", "water bottle"], "Very hot weather", "Cooling, sun protection, hydration and lightweight products are prioritized for the current heat.")
    if rain > 0.2:
        return (["umbrella", "raincoat", "waterproof shoes", "waterproof bag"], "Rainy conditions", "Weather-resistant products are prioritized because measurable rain is present.")
    if humidity >= 80:
        return (["dehumidifier", "fan", "moisture absorber", "quick dry clothes"], "High humidity", "Ventilation and moisture-control products are prioritized for high humidity.")
    if temp >= 30:
        return (["fan", "sunscreen", "water bottle", "cotton clothing", "air cooler"], "Warm weather", "Cooling, sun protection, hydration and lightweight products are prioritized.")
    return (["daily essentials", "home appliances", "personal care"], "Comfortable conditions", "Recommendations use the current weather but do not apply a strong weather preference.")


@app.get("/api/context-recommendations")
def context_recommendations():
    temp = safe_float(request.args.get("temperature"), 27)
    rain = safe_float(request.args.get("rain"), 0)
    humidity = safe_float(request.args.get("humidity"), 60)
    location = request.args.get("location", "")
    terms, headline, reason = weather_context(temp, rain, humidity)
    shopping_items = []
    enabled = False
    errors = []
    for term in terms[:6]:
        try:
            result = live_shopping(term, location=location, limit=8)
            enabled = enabled or result.get("enabled", False)
            shopping_items.extend(result.get("items", [])[:4])
            if result.get("error"): errors.append(result["error"])
        except Exception as exc:
            errors.append(str(exc))
    # Deduplicate by title + source.
    unique = {}
    for item in shopping_items:
        key = (item.get("title", "").lower(), item.get("source", "").lower())
        unique[key] = item
    return jsonify({"headline": headline, "reason": reason, "temperature": temp, "rain": rain, "humidity": humidity, "terms": terms, "shopping_enabled": enabled, "shopping": [normalise_shopping_item(x) for x in list(unique.values())[:18]], "errors": errors[:2]})


@app.get("/api/social-trend")
def social_trend():
    query = request.args.get("q", "ecommerce")
    try:
        return jsonify(fetch_social_trend(query))
    except Exception:
        return jsonify({"score": 50, "posts": 0, "source": "unavailable", "message": "Public trend service unavailable."})


@app.get("/api/best-value")
def best_value():
    q = request.args.get("q", "").strip()
    location = request.args.get("location", "").strip()
    if not q:
        return jsonify({"product": None, "alternatives": [], "message": "Search for a product first."})
    try:
        result = live_shopping(q, location=location, limit=40)
    except Exception as exc:
        return jsonify({"product": None, "alternatives": [], "message": str(exc)}), 503
    items = exact_intent_filter(result.get("items", []), q)
    scored = []
    prices = [safe_float(x.get("extracted_price"), 0) for x in items if safe_float(x.get("extracted_price"), 0) > 0]
    max_price = max(prices) if prices else 1
    for item in items:
        price = safe_float(item.get("extracted_price"), 0)
        if price <= 0:
            continue
        rating = safe_float(item.get("rating"), 0)
        reviews = safe_float(item.get("reviews"), 0)
        price_score = max(0, 30 * (1 - min(price / max_price, 1)))
        rating_score = (rating / 5) * 45 if rating else 20
        review_score = min(15, math.log10(reviews + 1) * 4) if reviews else 0
        delivery_score = 10 if item.get("delivery") else 0
        score = round(min(100, price_score + rating_score + review_score + delivery_score), 1)
        p = normalise_shopping_item(item)
        p["value_score"] = score
        scored.append(p)
    scored.sort(key=lambda x: x["value_score"], reverse=True)
    lowest = min((p for p in scored if safe_float(p.get("price"), 0) > 0), key=lambda x: safe_float(x.get("price"), 0), default=None)
    highest_rating = max(scored, key=lambda x: safe_float(x.get("rating"), 0), default=None)
    return jsonify({
        "product": scored[0] if scored else None,
        "lowest_price": lowest,
        "highest_rated": highest_rating,
        "alternatives": scored[1:8],
        "offer_count": len(scored),
        "price_range": {"min": min(prices) if prices else None, "max": max(prices) if prices else None},
        "source": result.get("source"),
        "live": result.get("enabled", False)
    })


@app.get("/api/bundle-options")
def bundle_options():
    context = request.args.get("context", "current").strip()
    location = request.args.get("location", "").strip()
    search = request.args.get("q", "").strip()
    if context == "current" and not search:
        search = "popular products"
    context_queries = {
        "beauty": "cleanser moisturizer sunscreen serum shampoo skincare",
        "fashion": "dress shirt jeans shoes bag fashion",
        "electronics": "smartphone laptop headphones smartwatch",
        "home": "air conditioner fan kitchen appliance home",
        "grocery": "groceries snacks beverages essentials",
        "sports": "running shoes sportswear fitness accessories",
        "travel": "travel bag luggage sunglasses travel accessories",
        "summer": "air cooler fan sunscreen water bottle cotton clothing",
    }
    if context in context_queries:
        search = context_queries[context]
    try:
        result = live_shopping(search, location=location, limit=40)
    except Exception as exc:
        return jsonify({"items": [], "enabled": False, "message": str(exc)}), 503
    unique = {}
    for item in result.get("items", []):
        p = normalise_shopping_item(item)
        if p["price"] is not None:
            unique[(p["title"].lower(), p["source"].lower())] = p
    return jsonify({"items": list(unique.values())[:30], "enabled": result.get("enabled", False), "source": result.get("source", ""), "query": search, "message": result.get("error", "")})


def derive_price_signals(selected, offers, social_trend=50, weather_factor=0.05):
    """Turn live shopping observations into model features automatically.
    These are transparent proxies for a student project; they are not seller-private metrics.
    """
    base = safe_float(selected.get("price"), 0)
    if base <= 0:
        base = safe_float(selected.get("extracted_price"), 0)
    priced = []
    for offer in offers or []:
        value = safe_float(offer.get("price", offer.get("extracted_price")), 0)
        if value > 0:
            priced.append(value)
    competitor_prices = [p for p in priced if abs(p - base) > 0.01]
    competitor = min(competitor_prices) if competitor_prices else round(base * 0.97, 2)
    rating = safe_float(selected.get("rating"), 4.2)
    reviews = safe_float(selected.get("reviews"), 0)
    old_price = safe_float(selected.get("old_price", selected.get("extracted_old_price")), 0)
    discount = round(max(0, (1 - base / old_price) * 100), 1) if old_price > base else 0

    review_signal = min(100, 35 + math.log10(reviews + 1) * 18) if reviews else 45
    rating_signal = max(0, min(100, rating / 5 * 100))
    demand = round(min(98, rating_signal * 0.55 + review_signal * 0.45), 1)
    popularity = round(min(98, 30 + math.log10(reviews + 1) * 20), 1) if reviews else 42
    # Return risk is a transparent proxy because public shopping feeds do not expose seller return rates.
    title = str(selected.get("title", "")).lower()
    return_risk = 38 if any(k in title for k in ["dress", "jeans", "shoe", "shirt", "top", "kurta", "saree"]) else 24
    return {
        "base_price": round(base, 2),
        "competitor_price": round(competitor, 2),
        "discount": discount,
        "rating": rating or 4.2,
        "demand_score": demand,
        "popularity_index": popularity,
        "social_trend": round(safe_float(social_trend, 50), 1),
        "return_risk": return_risk,
        "weather_impact": round(safe_float(weather_factor, 0.05), 3),
        "loyalty_score": 5,
        "sale_event": "normal",
    }


@app.post("/api/price-signals")
def price_signals():
    body = request.get_json(force=True) or {}
    selected = body.get("selected") or {}
    offers = body.get("offers") or []
    if not selected:
        return jsonify({"error": "Select a live offer first."}), 400
    return jsonify(derive_price_signals(selected, offers, body.get("social_trend", 50), body.get("weather_factor", 0.05)))


@app.post("/api/predict-price")
def predict():
    body = request.get_json(force=True) or {}
    product_name = body.get("product", "Custom Product")
    category = body.get("category", "General")
    base = safe_float(body.get("base_price"), 2499)
    competitor = safe_float(body.get("competitor_price"), base * 0.92)
    discount = safe_float(body.get("discount"), 10)
    rating = safe_float(body.get("rating"), 4.2)
    demand = safe_float(body.get("demand_score"), 70)
    popularity = safe_float(body.get("popularity_index"), 65)
    trend = safe_float(body.get("social_trend"), 60)
    return_risk = safe_float(body.get("return_risk"), 30)
    loyalty = safe_float(body.get("loyalty_score"), 25)
    weather_factor = safe_float(body.get("weather_impact"), 0.05)
    sale_event = body.get("sale_event", "normal")
    life = lifecycle_score(demand, popularity, trend)
    spike_score, spike_label = demand_spike(demand, trend, popularity)
    sale_factor = upcoming_sale_factor(sale_event)
    features = {"base_price": base, "competitor_price": competitor, "discount": discount, "rating": rating, "demand_score": demand, "popularity_index": popularity, "social_trend": trend, "return_risk": return_risk, "weather_impact": weather_factor, "loyalty_score": loyalty, "lifecycle_score": life}
    try:
        predicted = predict_price(features)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    predicted *= sale_factor
    if loyalty >= 80: predicted *= 0.97
    predicted = round(max(49, predicted), 2)
    strategy = choose_strategy(base, competitor, demand, trend, return_risk)
    row = {**features, "product": product_name, "category": category, "predicted_price": predicted, "strategy": strategy}
    add_prediction(row)
    return jsonify({"predicted_price": predicted, "currency": "INR", "strategy": strategy, "demand_spike": {"score": spike_score, "label": spike_label}, "lifecycle": {"score": life, "stage": ("Introduction" if life < 25 else "Growth" if life < 50 else "Maturity" if life < 75 else "Decline")}, "sale_event": sale_event, "sale_factor": sale_factor, "features": features})


@app.post("/api/analyze-review")
def review():
    body = request.get_json(force=True) or {}
    text = body.get("review", "")
    if not text.strip(): return jsonify({"error": "Review text is required"}), 400
    result = analyze_sentiment(text)
    with get_db() as conn:
        conn.execute("INSERT INTO reviews(review_text, sentiment, score) VALUES (?, ?, ?)", (text, result["sentiment"], result["score"]))
    return jsonify(result)


@app.post("/api/bundle-optimize")
def bundle():
    body = request.get_json(force=True) or {}
    items = body.get("items", [])
    prices = [safe_float(item.get("price"), 0) for item in items if isinstance(item, dict)]
    if len(prices) < 2: return jsonify({"error": "Select at least two live products"}), 400
    subtotal, optimized, discount = optimize_bundle(prices)
    with get_db() as conn:
        conn.execute("INSERT INTO bundle_requests(items, optimized_price, discount_percent) VALUES (?, ?, ?)", (", ".join(item.get("title", "Item") for item in items), optimized, discount))
    return jsonify({"items": items, "subtotal": subtotal, "optimized_price": optimized, "discount_percent": discount, "message": f"Bundle saves ₹{round(subtotal - optimized, 2)} based on the selected live prices."})


@app.post("/api/stylist")
def stylist():
    body = request.get_json(force=True) or {}
    user_type, outfit_type, season = body.get("user_type", "Women"), body.get("outfit_type", "Dress"), body.get("season", "Summer")
    result = stylist_recommendations(user_type, outfit_type, season, body.get("loyalty", "New"))
    qmap = {"dress":"women dress", "top":"women top", "shirt":"shirt", "shoes":"shoes", "casual":"casual fashion", "formal":"formal wear", "ethnic":"kurta ethnic wear", "sports":"sportswear"}
    query = qmap.get(str(outfit_type).lower(), f"{user_type} {outfit_type}")
    try:
        live = live_shopping(query, request.args.get("location", ""), 12)
        result["products"] = [normalise_shopping_item(x) for x in live.get("items", [])[:8]]
        result["live"] = live.get("enabled", False)
    except Exception:
        result["products"] = []
        result["live"] = False
    return jsonify(result)


@app.get("/api/try-on-products")
def try_on_products():
    q = request.args.get("q", "").strip()
    location = request.args.get("location", "").strip()
    query = q or "women dress shirt top shoes bag sunglasses fashion"
    try:
        result = live_shopping(query, location=location, limit=40)
    except Exception as exc:
        return jsonify({"items": [], "enabled": False, "message": str(exc)}), 503
    nonwearable = r"laptop|computer|phone|smartphone|tablet|fridge|refrigerator|microwave|television|tv|printer|keyboard|mouse|monitor|air conditioner|air cooler|fan|washing machine|vacuum|speaker|headphone|earbuds|grocery|shampoo|cleanser|moisturizer|serum|food|rice|oil|pan|furniture"
    items=[]
    for item in result.get("items", []):
        title=str(item.get("title", ""))
        if __import__('re').search(nonwearable, title, __import__('re').I):
            continue
        if not __import__('re').search(r"dress|shirt|top|shoe|sneaker|sandal|bag|handbag|watch|jewell|jewel|sunglass|jean|jacket|blazer|skirt|hoodie|kurta|saree|trouser|pant|shorts|fashion|clothing|apparel", title, __import__('re').I):
            continue
        items.append(normalise_shopping_item(item))
    return jsonify({"items": items[:30], "enabled": result.get("enabled", False), "source": result.get("source", ""), "message": result.get("error", "")})


@app.post("/api/try-on")
def try_on():
    """Generate a visual try-on using the uploaded person photo + live product image.
    Gemini image generation is optional and requires GEMINI_API_KEY.
    """
    import base64
    import uuid
    import requests as http_requests

    file = request.files.get("photo")
    outfit = request.form.get("outfit", "")
    product_image_url = request.form.get("product_image", "")
    if not file:
        return jsonify({"error": "Upload a photo first"}), 400
    if not os.getenv("GEMINI_API_KEY", "").strip():
        return jsonify({"error": "Virtual Try-On generation is not configured. Add GEMINI_API_KEY to .env."}), 503
    if not product_image_url:
        return jsonify({"error": "The selected wearable does not have a usable product image."}), 400

    try:
        from google import genai
        photo_bytes = file.read()
        photo_mime = file.mimetype or "image/jpeg"
        image_response = http_requests.get(product_image_url, timeout=15)
        image_response.raise_for_status()
        product_bytes = image_response.content
        product_mime = image_response.headers.get("content-type", "image/jpeg").split(";")[0]
        if not product_mime.startswith("image/"):
            product_mime = "image/jpeg"

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY").strip())
        prompt = f"""Create a realistic e-commerce virtual try-on image. Use the first image as the person reference and the second image as the exact clothing/accessory product reference. Put the person wearing the selected product: {outfit}. Preserve the person's face, body proportions, pose, skin tone and overall identity as much as possible. Reproduce the product's color, pattern, material, silhouette and important details faithfully. Do not add extra garments or accessories unless they are already present. Keep a natural full-body or three-quarter fashion-photo composition, realistic fabric folds, lighting and shadows. This is a product try-on, not a fashion illustration."""
        # google-genai >= 2.0 uses the current Interactions API schema.
        # The image-editing docs support multiple inline image inputs for
        # Gemini 3.1 Flash Image, which is what we use for person + garment.
        interaction = client.interactions.create(
            model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            input=[
                {"type": "text", "text": prompt},
                {"type": "image", "data": base64.b64encode(photo_bytes).decode("utf-8"), "mime_type": photo_mime},
                {"type": "image", "data": base64.b64encode(product_bytes).decode("utf-8"), "mime_type": product_mime},
            ],
            response_format={"type": "image", "aspect_ratio": "3:4", "image_size": "1K"},
        )
        output = getattr(interaction, "output_image", None)
        if not output or not getattr(output, "data", None):
            raise RuntimeError("Gemini returned no generated image.")
        generated = base64.b64decode(output.data)
        filename = f"tryon_{uuid.uuid4().hex}.png"
        destination = UPLOAD_DIR / filename
        destination.write_bytes(generated)
        return jsonify({
            "status": "generated",
            "outfit": outfit,
            "filename": filename,
            "image_url": f"/uploads/{filename}",
            "message": "Virtual try-on image generated successfully."
        })
    except Exception as exc:
        message = str(exc)
        if "429" in message or "rate limit" in message.lower() or "limit: 0 requests per day" in message.lower():
            return jsonify({
                "error": "Gemini image generation is not available on the current API project's free tier. The selected image model has 0 free-tier image requests; enable Gemini API billing/paid tier for this project, then try again.",
                "code": "GEMINI_IMAGE_QUOTA"
            }), 429
        return jsonify({"error": f"Virtual Try-On generation failed: {exc}"}), 502


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_DIR, filename)


@app.get("/api/history")
def history(): return jsonify({"predictions": recent_predictions(12)})


@app.get("/api/dashboard")
def dashboard():
    rows = recent_predictions(100)
    if not rows: return jsonify({"predictions": 0, "average_predicted_price": 0, "average_demand": 0, "average_return_risk": 0})
    return jsonify({"predictions": len(rows), "average_predicted_price": round(sum(r["predicted_price"] for r in rows) / len(rows), 2), "average_demand": round(sum(r["demand_score"] for r in rows) / len(rows), 1), "average_return_risk": round(sum(r["return_risk"] for r in rows) / len(rows), 1)})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
