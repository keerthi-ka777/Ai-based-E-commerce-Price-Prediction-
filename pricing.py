def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, float(value)))

def lifecycle_score(demand, popularity, trend):
    # 0-25 introduction, 25-50 growth, 50-75 maturity, 75-100 decline is
    # represented as a continuous score for the ML model.
    score = (demand * 0.45 + popularity * 0.30 + trend * 0.25)
    return round(clamp(score), 2)

def demand_spike(demand, trend, popularity):
    score = demand * 0.45 + trend * 0.35 + popularity * 0.20
    if score >= 78:
        label = "High spike risk"
    elif score >= 60:
        label = "Moderate spike risk"
    else:
        label = "Stable demand"
    return round(score, 1), label

def choose_strategy(base, competitor, demand, trend, return_risk):
    if demand >= 75 and trend >= 70:
        return "Increase price slightly because demand and trend signals are high."
    if competitor < base * 0.9:
        return "Keep the price competitive; consider a bundle or loyalty offer."
    if return_risk >= 60:
        return "Reduce price slightly or improve product information to reduce return risk."
    return "Keep the price near the market level and monitor demand."

def optimize_bundle(prices, bundle_discount=0.15):
    subtotal = sum(prices)
    optimized = subtotal * (1 - bundle_discount)
    return round(subtotal, 2), round(optimized, 2), round(bundle_discount * 100, 1)

def upcoming_sale_factor(event):
    event = (event or "").lower()
    factors = {
        "diwali": 1.10,
        "big billion": 1.08,
        "independence day": 1.05,
        "new year": 1.06,
        "summer sale": 1.07,
        "flash sale": 1.12,
        "normal": 1.00,
    }
    return factors.get(event, 1.03)
