"""
Sentiment analysis and keyword extraction engine.
Rule-based approach for Turkish/English reviews with category-specific keyword detection.
"""

import re
import json

# ── Sentiment Keyword Dictionaries ─────────────────────────────

POSITIVE_WORDS_TR = {
    "mükemmel", "harika", "süper", "muhteşem", "güzel", "temiz", "hızlı", "ilgili",
    "kaliteli", "başarılı", "profesyonel", "memnun", "tavsiye", "ederim", "beğendim",
    "lezzetli", "ferah", "samimi", "nazik", "güleryüzlü", "uygun", "rahat",
    "kusursuz", "olağanüstü", "enfes", "tatmin", "şahane", "inanılmaz",
    "teşekkür", "bravo", "helal", "efsane", "bomba", "bayıldım", "âlâ",
}

NEGATIVE_WORDS_TR = {
    "kötü", "berbat", "rezalet", "pahalı", "pis", "yavaş", "ilgisiz", "soğuk",
    "kaba", "kırık", "bozuk", "leş", "iğrenç", "korkunç", "vasat", "yetersiz",
    "hayal kırıklığı", "boktan", "dandik", "çöp", "fiyasko", "skandal",
    "bekledim", "beklettiler", "umursamaz", "saygısız", "kirli", "küflü",
    "bayat", "kokmuş", "iade", "şikayet", "aldatma", "dolandır",
}

POSITIVE_WORDS_EN = {
    "excellent", "amazing", "great", "wonderful", "clean", "fast", "friendly",
    "professional", "quality", "recommend", "delicious", "perfect", "outstanding",
    "fantastic", "love", "best", "awesome", "brilliant", "superb", "satisfied",
    "fresh", "cozy", "warm", "comfortable", "impressive", "phenomenal",
}

NEGATIVE_WORDS_EN = {
    "bad", "terrible", "awful", "dirty", "slow", "rude", "expensive", "overpriced",
    "worst", "disgusting", "horrible", "poor", "disappointing", "cold", "stale",
    "broken", "unprofessional", "unfriendly", "complaint", "refund", "scam",
    "waste", "mediocre", "nasty", "gross", "soggy", "undercooked", "burnt",
}

# ── Category-Specific Keywords ────────────────────────────────

CATEGORY_KEYWORDS = {
    "default": {
        "tr": ["fiyat", "temizlik", "hizmet", "personel", "kalite", "ambiyans", "bekleme", "konum",
               "hijyen", "iletişim", "randevu", "park", "ulaşım", "ilgi", "güler yüz"],
        "en": ["price", "cleanliness", "service", "staff", "quality", "ambiance", "wait",
               "location", "hygiene", "communication", "appointment", "parking", "atmosphere"],
    },
    "restoran": {
        "tr": ["lezzet", "porsiyon", "menü", "garson", "servis", "fiyat", "ambiyans", "temizlik",
               "bekleme", "rezervasyon", "taze", "sunum", "içecek", "tatlı", "kahvaltı",
               "akşam yemeği", "öğle", "mutfak", "şef", "masa", "bahçe"],
        "en": ["taste", "portion", "menu", "waiter", "service", "price", "ambiance", "fresh",
               "reservation", "presentation", "drink", "dessert", "breakfast", "dinner", "chef"],
    },
    "kafe": {
        "tr": ["kahve", "lezzet", "ambiyans", "fiyat", "servis", "oturma", "wifi",
               "tatlı", "müzik", "dekorasyon", "temizlik", "çalışma", "atmosfer"],
        "en": ["coffee", "taste", "ambiance", "price", "service", "seating", "wifi",
               "pastry", "music", "decor", "atmosphere", "work"],
    },
    "berber": {
        "tr": ["saç", "kesim", "fiyat", "hijyen", "randevu", "bekleme", "usta",
               "tıraş", "sakal", "bakım", "şekil", "yıkama", "kuaför"],
        "en": ["haircut", "style", "price", "hygiene", "appointment", "wait", "barber",
               "shave", "beard", "trim", "wash", "fade"],
    },
    "otel": {
        "tr": ["oda", "temizlik", "kahvaltı", "personel", "konum", "fiyat", "havuz",
               "spa", "resepsiyon", "gürültü", "yatak", "banyo", "manzara", "otopark"],
        "en": ["room", "cleanliness", "breakfast", "staff", "location", "price", "pool",
               "spa", "reception", "noise", "bed", "bathroom", "view", "parking"],
    },
    "bar": {
        "tr": ["kokteyl", "müzik", "ambiyans", "fiyat", "servis", "kalabalık",
               "içki", "DJ", "atmosfer", "güvenlik", "oturma"],
        "en": ["cocktail", "music", "ambiance", "price", "service", "crowd",
               "drink", "DJ", "atmosphere", "security", "seating"],
    },
    "lounge": {
        "tr": ["ambiyans", "müzik", "kokteyl", "servis", "fiyat", "dekorasyon",
               "VIP", "rezervasyon", "atmosfer", "menü"],
        "en": ["ambiance", "music", "cocktail", "service", "price", "decor",
               "VIP", "reservation", "atmosphere", "menu"],
    },
}


def detect_language(text):
    """Simple language detection: Turkish vs English."""
    tr_chars = set("çğıöşüÇĞİÖŞÜ")
    if any(c in tr_chars for c in text):
        return "tr"
    # Heuristic: check for common Turkish words
    tr_common = {"ve", "bir", "bu", "da", "de", "ile", "için", "çok", "ama", "var"}
    words = set(text.lower().split())
    if len(words & tr_common) >= 2:
        return "tr"
    return "en"


def analyze_sentiment(text, rating=0):
    """
    Analyze sentiment of a review text.
    Returns: 'positive', 'negative', or 'neutral'
    Uses both keyword matching and rating correlation.
    """
    if not text:
        return "neutral"

    text_lower = text.lower()
    lang = detect_language(text)

    pos_words = POSITIVE_WORDS_TR if lang == "tr" else POSITIVE_WORDS_EN
    neg_words = NEGATIVE_WORDS_TR if lang == "tr" else NEGATIVE_WORDS_EN

    pos_count = sum(1 for w in pos_words if w in text_lower)
    neg_count = sum(1 for w in neg_words if w in text_lower)

    # Rating-based boost
    if rating >= 4:
        pos_count += 2
    elif rating <= 2:
        neg_count += 2
    elif rating == 3:
        pass  # neutral boost

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    else:
        # Tie-break with rating
        if rating >= 4:
            return "positive"
        elif rating <= 2:
            return "negative"
        return "neutral"


def extract_keywords(text, category="default"):
    """
    Extract category-specific keywords from review text.
    Returns list of matched keywords.
    """
    if not text:
        return []

    text_lower = text.lower()
    lang = detect_language(text)

    # Get category keywords, fall back to default
    cat_lower = category.lower().strip()
    cat_config = CATEGORY_KEYWORDS.get(cat_lower, CATEGORY_KEYWORDS["default"])
    keywords = cat_config.get(lang, cat_config.get("tr", []))

    # Also include default keywords
    default_kws = CATEGORY_KEYWORDS["default"].get(lang, [])
    all_keywords = list(set(keywords + default_kws))

    found = []
    for kw in all_keywords:
        if kw.lower() in text_lower:
            found.append(kw)

    return found


def process_review(text, rating=0, category="default"):
    """
    Full processing of a single review.
    Returns dict with sentiment and keywords.
    """
    return {
        "sentiment": analyze_sentiment(text, rating),
        "keywords": extract_keywords(text, category),
    }


def process_reviews_batch(reviews, category="default"):
    """
    Process a batch of reviews.
    reviews: list of dicts with 'text' and 'rating' keys.
    Returns list of dicts with added 'sentiment' and 'keywords'.
    """
    processed = []
    for rev in reviews:
        result = process_review(rev.get("text", ""), rev.get("rating", 0), category)
        enriched = {**rev, **result}
        processed.append(enriched)
    return processed


def compute_sentiment_score(reviews):
    """
    Compute a 0-100 sentiment score from a list of reviews.
    100 = all positive, 0 = all negative.
    """
    if not reviews:
        return 50

    pos = sum(1 for r in reviews if r.get("sentiment") == "positive")
    neg = sum(1 for r in reviews if r.get("sentiment") == "negative")
    total = len(reviews)

    if total == 0:
        return 50

    return round((pos / total) * 100)


def detect_opportunities(bad_reviews, min_count=3):
    """
    Detect competitor weaknesses from bad reviews.
    Groups by keyword and returns top opportunities.
    """
    keyword_issues = {}
    for rev in bad_reviews:
        keywords = rev.get("keywords", [])
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except:
                keywords = []
        for kw in keywords:
            if kw not in keyword_issues:
                keyword_issues[kw] = {"count": 0, "examples": []}
            keyword_issues[kw]["count"] += 1
            if len(keyword_issues[kw]["examples"]) < 3:
                keyword_issues[kw]["examples"].append(rev.get("text", "")[:100])

    # Filter by minimum count and sort
    opportunities = [
        {"keyword": kw, **data}
        for kw, data in keyword_issues.items()
        if data["count"] >= min_count
    ]
    opportunities.sort(key=lambda x: x["count"], reverse=True)
    return opportunities[:10]
