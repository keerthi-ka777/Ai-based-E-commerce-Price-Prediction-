import math
import os
import requests
import re
from urllib.parse import urlparse

WEATHER_API = "https://api.open-meteo.com/v1/forecast"
GEOCODING_API = "https://geocoding-api.open-meteo.com/v1/search"
SERPAPI_URL = "https://serpapi.com/search"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"


def _get(url, **kwargs):
    kwargs.setdefault("timeout", 10)
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return response


def fetch_weather(lat, lon):
    response = _get(
        WEATHER_API,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "hourly": "temperature_2m,precipitation_probability,precipitation",
            "forecast_days": 1,
            "timezone": "auto",
        },
    )
    return response.json()


def geocode_city(query):
    response = _get(
        GEOCODING_API,
        params={"name": query, "count": 5, "language": "en", "format": "json"},
    )
    return response.json().get("results", [])


def search_location(query):
    """Resolve a city, locality, or Indian PIN code to coordinates and address.

    Indian 6-digit PIN codes are handled explicitly through the India Post
    public lookup, then geocoded to coordinates for weather. This means a PIN
    such as 560103 can be used directly instead of requiring browser location.
    """
    q = (query or "").strip()
    if not q:
        return []

    pin = re.fullmatch(r"\d{6}", q)
    candidates = []
    if pin:
        try:
            post = _get(f"https://api.postalpincode.in/pincode/{q}").json()
            rows = (post[0].get("PostOffice") or []) if isinstance(post, list) and post else []
            for row in rows[:8]:
                candidates.append({
                    "name": row.get("Name", ""),
                    "district": row.get("District", ""),
                    "state": row.get("State", ""),
                    "country": "India",
                    "postcode": q,
                })
        except Exception:
            candidates = []

    # Nominatim gives the best locality-level coordinates when available.
    nom_queries = []
    if candidates:
        for c in candidates[:5]:
            nom_queries.append(f"{c['name']}, {c['district']}, {c['state']}, India")
        nom_queries.append(f"{q}, India")
    else:
        nom_queries.append(q if re.search(r"\D", q) else f"{q}, India")

    for nom_q in nom_queries:
        try:
            response = _get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": nom_q,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": 8,
                    "countrycodes": "in",
                },
                headers={"User-Agent": "AI-Ecommerce-Student-Project/5.0"},
            )
            rows = response.json()
            results = []
            for row in rows:
                address = row.get("address", {})
                city = (address.get("city") or address.get("town") or address.get("village")
                        or address.get("municipality") or address.get("county") or address.get("suburb") or "")
                state = address.get("state", "")
                postcode = address.get("postcode", "") or (q if pin else "")
                results.append({
                    "latitude": float(row.get("lat")),
                    "longitude": float(row.get("lon")),
                    "name": row.get("name") or city or q,
                    "city": city,
                    "state": state,
                    "country": address.get("country", "India"),
                    "postcode": postcode,
                    "display_name": row.get("display_name", ""),
                    "type": row.get("type", ""),
                })
            if results:
                return results
        except Exception:
            continue

    # Final fallback for a PIN: use the postal office/locality name with
    # Open-Meteo's city geocoder so weather still works if Nominatim is down.
    if candidates:
        fallback = []
        seen = set()
        for c in candidates:
            name = c.get("name", "")
            query_text = f"{name}, {c.get('district','')}, {c.get('state','')}"
            try:
                rows = geocode_city(query_text)
            except Exception:
                rows = []
            for row in rows[:2]:
                key = (row.get("latitude"), row.get("longitude"))
                if key in seen:
                    continue
                seen.add(key)
                fallback.append({
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "name": row.get("name") or name,
                    "city": row.get("name") or c.get("district", ""),
                    "state": row.get("admin1") or c.get("state", ""),
                    "country": row.get("country") or "India",
                    "postcode": q,
                    "display_name": f"{name}, {c.get('district','')}, {c.get('state','')}, India",
                })
        return fallback
    return []

def weather_impact(weather: dict, category: str) -> float:
    current = weather.get("current", {})
    rain = float(current.get("precipitation", 0) or 0)
    temp = float(current.get("temperature_2m", 25) or 25)
    cat = (category or "").lower()
    impact = 0.0
    if rain > 0.2 and any(k in cat for k in ["umbrella", "rain", "fashion", "shoe", "tops", "dress"]):
        impact += 0.25
    if temp >= 30 and any(k in cat for k in ["beauty", "fragrance", "fashion", "shirt", "dress", "skin"]):
        impact += 0.12
    if temp >= 32 and any(k in cat for k in ["laptop", "electronics", "smartphone"]):
        impact += 0.05
    return min(1.0, impact)


def fetch_social_trend(query: str):
    """Best-effort public Reddit signal; it is not a private social-media feed."""
    query = (query or "ecommerce").strip()
    response = _get(
        "https://www.reddit.com/search.json",
        params={"q": query, "sort": "hot", "limit": 20, "t": "week"},
        headers={"User-Agent": "AI-Ecommerce-Student-Project/2.0"},
    )
    children = response.json().get("data", {}).get("children", [])
    posts = [x.get("data", {}) for x in children]
    if not posts:
        return {"score": 50, "posts": 0, "source": "fallback"}
    engagement = sum(
        float(p.get("score", 0) or 0) + float(p.get("num_comments", 0) or 0) * 0.5
        for p in posts
    )
    score = min(100, round(35 + math.log1p(max(0, engagement)) * 5, 1))
    return {"score": score, "posts": len(posts), "source": "Reddit public search"}


def reverse_geocode(lat, lon):
    """Resolve browser coordinates to a human-readable city/state/country.
    Location is only used for the current request; the app does not persist it.
    """
    response = _get(
        NOMINATIM_URL,
        params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10, "addressdetails": 1},
        headers={"User-Agent": "AI-Ecommerce-Student-Project/4.0"},
    )
    data = response.json()
    address = data.get("address", {})
    city = address.get("city") or address.get("town") or address.get("village") or address.get("municipality") or address.get("county") or ""
    state = address.get("state", "")
    country = address.get("country", "")
    postcode = address.get("postcode", "")
    return {"city": city, "state": state, "country": country, "postcode": postcode, "display_name": data.get("display_name", "")}


def _shopping_query(query):
    """Make common brand+generic searches precise without changing the user's intent."""
    q = (query or "").strip()
    low = q.lower()
    if "cetaphil" in low and "cleanser" in low:
        return "Cetaphil Gentle Skin Cleanser"
    return q

def _retailer_key(item):
    """Use the retailer/domain so duplicate Google Shopping listings collapse,
    while different retailers remain visible."""
    url = str(item.get("product_link") or item.get("url") or "").strip()
    try:
        host = urlparse(url).netloc.lower().split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        if host:
            return host
    except Exception:
        pass
    source = str(item.get("source", "")).lower().strip()
    source = re.sub(r"\s+", " ", source)
    source = re.split(r"\s+-\s+", source, maxsplit=1)[0]
    return source

def _product_key(title):
    text = str(title or "").lower()
    text = re.sub(r"\b(big billion days|nykaa sale|sale|limited time offer|deal)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def search_google_shopping(query, location="", limit=40):
    """Current Google Shopping results through SerpApi.
    Different retailers are preserved; duplicate listings from the same retailer
    for the same product are collapsed to the cheapest usable offer.
    """
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        return {"enabled": False, "source": "Google Shopping via SerpApi", "items": [], "query": query, "location": location}
    params = {
        "engine": "google_shopping",
        # Keep the user's original shopping phrase. Do not rewrite
        # "cetaphil cleanser" to a single product variant; Google Shopping
        # should return the full set of matching retailers, sizes and packs.
        "q": str(query or "").strip(),
        "api_key": key,
        "gl": "in",
        "hl": "en",
        "num": min(max(int(limit), 1), 40),
    }
    # A raw Indian PIN code is useful for our weather/location features, but
    # passing it directly to SerpApi Google Shopping can drastically narrow
    # the shopping feed. Keep PIN handling in the app while requesting the
    # broad India shopping feed. City/locality strings can still be used.
    if location and not re.fullmatch(r"\d{6}", str(location).strip()):
        params["location"] = location
    response = _get(SERPAPI_URL, params=params)
    payload = response.json()
    raw_items = payload.get("shopping_results", [])

    # Google Shopping can return several promotional/listing variants from the
    # same retailer. Keep one useful offer per retailer/product, but never merge
    # different retailers. This fixes repeated Purplle listings while retaining
    # Apollo, Nykaa, Amazon, Flipkart, etc. when they are present in the feed.
    unique = {}
    for item in raw_items:
        title = item.get("title", "")
        retailer = _retailer_key(item)
        product = _product_key(title)
        key_tuple = (retailer, product)
        existing = unique.get(key_tuple)
        price = item.get("extracted_price")
        if existing is None:
            unique[key_tuple] = item
        else:
            old_price = existing.get("extracted_price")
            try:
                if price is not None and (old_price is None or float(price) < float(old_price)):
                    unique[key_tuple] = item
            except (TypeError, ValueError):
                pass

    items = []
    for item in unique.values():
        items.append({
            "id": f"shop-{item.get('product_id') or item.get('position') or len(items)}",
            "title": item.get("title", ""),
            "source": item.get("source", "Google Shopping"),
            "source_icon": item.get("source_icon", ""),
            "price": item.get("price"),
            "extracted_price": item.get("extracted_price"),
            "old_price": item.get("old_price"),
            "extracted_old_price": item.get("extracted_old_price"),
            "delivery": item.get("delivery", ""),
            "rating": item.get("rating"),
            "reviews": item.get("reviews"),
            "snippet": item.get("snippet", ""),
            "thumbnail": item.get("thumbnail", ""),
            "url": item.get("product_link", ""),
            "tag": item.get("tag", ""),
            "multiple_sources": bool(item.get("multiple_sources")),
        })
    return {"enabled": True, "source": "Google Shopping via SerpApi", "items": items[:limit], "query": str(query or "").strip(), "location": location}



def live_shopping(query, location="", limit=40):
    """Unified live-shopping function used by the Flask application."""
    try:
        result = search_google_shopping(query=query, location=location, limit=limit)
        return {
            "enabled": result.get("enabled", False),
            "source": result.get("source", "Google Shopping via SerpApi"),
            "items": result.get("items", []),
            "query": result.get("query", query),
            "location": result.get("location", location),
            "error": result.get("error", ""),
        }
    except Exception as exc:
        return {
            "enabled": False,
            "source": "Google Shopping via SerpApi",
            "items": [],
            "query": query,
            "location": location,
            "error": str(exc),
        }
