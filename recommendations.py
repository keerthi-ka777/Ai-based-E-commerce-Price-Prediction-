def stylist_recommendations(user_type, outfit_type, season, loyalty="New"):
    season = (season or "Summer").lower()
    outfit = (outfit_type or "Dress").lower()

    palette = {
        "summer": ["cotton", "linen", "lightweight layers"],
        "winter": ["knit", "wool blend", "layered jacket"],
        "monsoon": ["quick-dry", "water-resistant", "easy-care"],
        "spring": ["pastel", "light cotton", "casual layers"],
    }.get(season, ["comfortable", "versatile", "easy-care"])

    looks = {
        "dress": ["Cotton midi dress", "Minimal sandals", "Structured handbag"],
        "casual": ["Relaxed shirt", "Straight-fit jeans", "Sneakers"],
        "formal": ["Solid shirt/blazer", "Tailored trousers", "Formal shoes"],
        "ethnic": ["Kurta", "Straight pants", "Traditional footwear"],
        "sports": ["Breathable tee", "Track pants", "Running shoes"],
    }.get(outfit, ["Versatile top", "Comfortable bottoms", "Neutral footwear"])

    loyalty_offer = {
        "new": "Welcome offer: 5% suggested discount",
        "silver": "Silver loyalty: 7% suggested discount",
        "gold": "Gold loyalty: 10% suggested discount",
        "platinum": "Platinum loyalty: 12% suggested discount",
    }.get((loyalty or "new").lower(), "5% suggested discount")

    return {
        "materials": palette,
        "looks": looks,
        "loyalty_offer": loyalty_offer,
        "message": f"For {user_type} customers, choose {outfit_type} pieces suitable for {season}."
    }
