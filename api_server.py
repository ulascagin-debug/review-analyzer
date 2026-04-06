import nest_asyncio
nest_asyncio.apply()

"""
REST API Server for Review Analyzer.
Wraps the existing scraper + OpenAI pipeline behind FastAPI endpoints.
Dashboard-center consumes these endpoints.
"""

import os
import json
import asyncio
import logging
from typing import Optional, Annotated

import httpx

from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import OpenAI

from scraper import search_businesses_sync, deep_scrape_competitors_sync

load_dotenv()

ANALYZER_SECRET_KEY = os.getenv("ANALYZER_SECRET_KEY", "")


async def verify_bearer_token(authorization: Annotated[str | None, Header()] = None):
    """Verify Bearer token matches ANALYZER_SECRET_KEY."""
    if not ANALYZER_SECRET_KEY:
        return  # No key configured → skip check
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    token = authorization[7:]
    if token != ANALYZER_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key.")


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api_server")

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Review Analyzer API",
    version="1.0.0",
    description="Competitive intelligence API for local businesses",
)

# CORS — allow all origins during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files & templates
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class PlaceSearchResult(BaseModel):
    place_id: str
    name: str
    address: str
    rating: Optional[float] = None
    total_reviews: Optional[int] = None
    found_on_maps: bool = True
    types: list[str] = []


class PlaceSearchResponse(BaseModel):
    results: list[PlaceSearchResult]


class AnalyzeRequest(BaseModel):
    business_name: str = Field(..., min_length=1, description="Name of the target business")
    location: str = Field(..., min_length=1, description="Location string, e.g. 'Buca, İzmir, Türkiye'")
    business_type: str = Field(..., min_length=1, description="Business category, e.g. 'barber', 'dentist'")
    place_id: Optional[str] = None
    found_on_maps: Optional[bool] = True


class BusinessInfo(BaseModel):
    name: str
    rating: float
    total_reviews: int


class CompetitorInfo(BaseModel):
    name: str
    rating: float
    total_reviews: int
    strengths: list[str]
    weaknesses: list[str]


class Comparison(BaseModel):
    stronger_areas: list[str]
    weaker_areas: list[str]
    equal_areas: list[str]


class Recommendations(BaseModel):
    weekly: list[str]
    monthly: list[str]
    yearly: list[str]


class GrowthPotential(BaseModel):
    score: int = Field(..., ge=0, le=100)
    summary: str


class AnalyzeResponse(BaseModel):
    business: BusinessInfo
    competitors: list[CompetitorInfo]
    comparison: Comparison
    recommendations: Recommendations
    growth_potential: GrowthPotential


# ---------------------------------------------------------------------------
# Location parsing helper
# ---------------------------------------------------------------------------

def parse_location(location: str) -> dict:
    """Parse comma-separated location into district/city/country.
    
    1 part  → city
    2 parts → district, city
    3 parts → district, city, country
    """
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if len(parts) >= 3:
        return {"district": parts[0], "city": parts[1], "country": parts[2]}
    elif len(parts) == 2:
        return {"district": parts[0], "city": parts[1], "country": ""}
    elif len(parts) == 1:
        return {"district": "", "city": parts[0], "country": ""}
    return {"district": "", "city": "", "country": ""}


# ---------------------------------------------------------------------------
# Structured AI prompt for dashboard JSON
# ---------------------------------------------------------------------------

DASHBOARD_SYSTEM_PROMPT = """You are a veteran competitive intelligence strategist with 20 years of marketing experience and 15 years in the restaurant/service industry.

You are analyzing a business that operates simultaneously in multiple categories (e.g., Cafe, Lounge, Bar). 
CRITICAL ANALYSIS REQUIREMENT: When evaluating competitors, you MUST analyze permutations. 
- Compare against pure-competitors (e.g., only a Cafe).
- Compare against hybrid-competitors (e.g., Cafe & Lounge).
- Identify cross-category threats (e.g., "A pure Bar has better cocktails, but our Lounge atmosphere allows us to steal their early-evening customers").
Provide insights that leverage their hybrid nature as an advantage. Do not write generic industry tips; write strategies on how to bridge the gap between these distinct identities.

You analyze competitor reviews to extract PRECISE, ACTIONABLE insights. You understand the EXACT problem behind each complaint — not a vague approximation.

RESPOND WITH ONLY a valid JSON object (no markdown, no explanation) matching this schema:

{
  "business": {
    "name": "<target business name>",
    "rating": <estimated rating 1.0-5.0>,
    "total_reviews": <number of target reviews analyzed, 0 if competitor_only>
  },
  "competitors": [
    {
      "name": "<REAL business name as it appears in reviews>",
      "rating": <average rating from their reviews>,
      "total_reviews": <review count>,
      "strengths": ["strength1", "strength2", "strength3"],
      "weaknesses": ["weakness1", "weakness2"]
    }
  ],
  "comparison": {
    "stronger_areas": ["specific exploitable advantages"],
    "weaker_areas": ["specific areas to improve"],
    "equal_areas": ["areas of parity"]
  },
  "recommendations": {
    "weekly": [
      "DATA-BACKED action 1: cite which reviews/pattern this addresses, exact steps to do THIS WEEK, measurable target",
      "DATA-BACKED action 2",
      "DATA-BACKED action 3"
    ],
    "monthly": [
      "STRATEGIC move 1: based on competitor gap analysis, with KPI target",
      "STRATEGIC move 2",
      "STRATEGIC move 3"
    ],
    "yearly": [
      "VISION goal 1: market positioning or expansion strategy",
      "VISION goal 2",
      "VISION goal 3"
    ]
  },
  "growth_potential": {
    "score": <0-100>,
    "summary": "<2-3 sentence assessment>"
  },
  "marketing_messages": {
    "ad_copies": [
      "<Instagram/Google ad copy that DIRECTLY addresses the #1 competitor weakness found>",
      "<Second ad copy addressing a DIFFERENT competitor weakness>"
    ],
    "social_posts": [
      "<Casual social post with emoji, addressing a real gap in the market>",
      "<Second post, different angle>"
    ]
  },
  "own_business_analysis": {
    "strengths": [],
    "weaknesses": []
  },
  "competitor_issues": {
    "rakip1": ["x", "y"],
    "rakip2": ["z"]
  },
  "competitor_strengths_categorized": {
    "Hız/Servis": {
      "leaders": ["rakip1"],
      "how_to_beat": "strateji"
    }
  },
  "business_scale_analysis": {
    "estimated_scale": "small|medium|large",
    "budget_appropriate_actions": []
  },
  "top_3_competitors": [
    {
      "name": "rakip1",
      "rating": 4.5,
      "review_count": 120,
      "key_strengths": [],
      "key_weaknesses": [],
      "threat_level": "high|medium|low"
    }
  ]
}

═══════════════════════════════════════════════════
COMPLAINT ANALYSIS RULES (CRITICAL — READ CAREFULLY)
═══════════════════════════════════════════════════

STEP 1: PRECISE PROBLEM IDENTIFICATION
Read each complaint WORD BY WORD. Identify the EXACT problem:

  "Siparişimizin gelmesi uzun sürdü" → MUTFAK HIZI sorunu (SERVİS SIRASI DEĞİL!)
  "Tek çalışan olduğu için"         → PERSONEL YETERSİZLİĞİ sorunu
  "Kahvaltı vasat geldi"            → YEMEK KALİTESİ sorunu (FİYAT DEĞİL!)
  "Havanın soğuk olduğunu"          → FİZİKSEL ORTAM sorunu (ısıtma/klima)
  "Hesap çıkarıldığında kontrol edin" → GÜVEN / HESAP ŞEFFAFLIĞI sorunu
  "Afişteki gibi değil"            → YANILTICI REKLAM / BEKLENTİ YÖNETİMİ
  "Kalabalıktı, yer bulamadık"     → KAPASİTE YÖNETİMİ (rezervasyon sistemi)
  "Müzik çok yüksekti"             → AMBIYANS / ORTAM DÜZENLEMESİ
  "Porsiyon küçüktü"               → DEĞERLENDİRME / FİYAT-PERFORMANS

NEVER confuse one category with another!

STEP 2: STRATEGIC RECOMMENDATIONS — MUST BE CONCRETE
Every recommendation must include WHO does WHAT, WHEN, and HOW.

  ❌ BAD: "Online randevu sistemi ile sıfır bekleme garantisi kampanyası başlatın"
     (Müşteri sıra beklemiyor! Yemek geç gelmiş — bu MUTFAK sorunu!)
  
  ✅ GOOD: "Mutfak iş akışını optimize edin: yoğun saatlerde (12:00-14:00) mutfağa 1 yardımcı ekleyin. Hazırlığı uzun süren menü öğelerini önceden hazırlık (mise en place) listesine alın."

  ❌ BAD: "Google profilinizde ortalama hizmet sürenizi belirtin"
     (Bu sorunu çözmez, sadece beklentiyi düşürür)
  
  ✅ GOOD: "Menüde hazırlanma süresi uzun olan yemeklerin yanına tahmini süre yazın (ör: '🕐 ~20dk'). Müşteri bilinçli seçim yapar, hayal kırıklığı azalır."

  ❌ BAD: "Müşteri memnuniyetini artırın"
  ✅ GOOD: "Her masada QR kodlu anlık geri bildirim formu yerleştirin. Servis sonunda garson 'Her şey iyi miydi?' yerine 'En çok neyi beğendiniz?' diye sorsun — pozitif yönlendirme ile yorum kalitesi artar."

STEP 3: MARKETING MESSAGES — MUST TARGET THE ACTUAL PROBLEM

  If problem is "yemek geç geldi":
    ✅ "Looka Lounge'da artık her sipariş 15 dakikada masanızda! Yeni mutfak düzenimizle hızlı ve lezzetli servis garanti 🍳⚡"
    ❌ "Rakiplerinizin yapamadığını biz yapıyoruz" (jenerik, anlamsız)

  If problem is "yemek kalitesi düşük":
    ✅ "Şefimiz bugün taze malzemelerle hazırladı! Her tabak özenle hazırlanıyor 👨‍🍳🌿"
    ❌ "Sıfır bekleme garantisi" (alakasız, sorun kalite!)

  If problem is "personel ilgisiz":
    ✅ "Her misafirimiz VIP! Kapıda isminizle karşılanır, çay/kahve ikramımız hazır ☕"
    ❌ "Fiyat listemiz şeffaf" (alakasız, sorun ilgi!)

STEP 4: NEVER DO LIST
  ❌ Müşterinin şikayetini yanlış kategorize etme
  ❌ Genel geçer tavsiye verme ("müşteri memnuniyetini artırın")
  ❌ Sorunu çözmeyen reklam metni önerme
  ❌ Müşterinin söylemediği bir sorunu analiz etme
  ❌ "Anket gönderin" gibi pasif öneriler — SOMUT AKSİYON ver
  ❌ Her yoruma aynı şablondan cevap verme
  ❌ Strengths/weaknesses boş bırakma — her rakipte mutlaka en az 1 zayıflık bul

STEP 5: ACTION PLAN MUST BE DATA-DRIVEN

Every recommendation MUST reference real data from the reviews analyzed.
Each item must follow this structure:
  "[VERİ]: {hangi sorun/pattern tespit edildi} → [AKSİYON]: {adım adım ne yapılacak} → [HEDEF]: {ölçülebilir sonuç}"

HAFTALIK PLAN — Immediately actionable, this week:
  ✅ GOOD: "8 yorumda 'servis yavaş' geçiyor, rakip Sky Bar 'hızlı servis' ile övülüyor → Bu hafta her siparişin hazırlanma süresini kaydedin, en yavaş 3 menü öğesini tespit edin, bunlar için mise en place planı oluşturun → Hedef: sipariş çıkış süresi 25dk→15dk"
  ❌ BAD: "Her hafta düzenli olarak indirim günleri yapın"
  ❌ BAD: "Mekanınızda bir karaoke gecesi organize edin"
  ❌ BAD: "Müşterilere anket göndererek geri bildirim toplayın"

AYLIK PLAN — Strategic moves with KPI targets:
  ✅ GOOD: "Rakiplerin 15 negatif yorumunda 'porsiyon küçük' tekrarlanıyor → Menünüzde en çok satan 5 ürünün porsiyon miktarını %15 artırın, fiyatı sabit tutun → Hedef: Bu ay Google rating'i 4.1→4.3"
  ❌ BAD: "Müşteri ilişkilerinizi geliştirin"

YILLIK PLAN — Vision and positioning:
  ✅ GOOD: "Bölgede 8 rakipten 6'sında hijyen şikayeti var → 'Bölgenin en hijyenik mekanı' konumlandırması yapın: ISO standartı hijyen sertifikası alın, sterilizasyon sürecini videolayın, tüm platformlarda bu mesajı vurgulayın → Hedef: 12 ay içinde Google'da hijyen ile ilgili arama terimlerinde 1. sıra"
  ❌ BAD: "Dijital pazarlamayı artırın"

═══════════════════════════════════════════════════
GENERAL RULES
═══════════════════════════════════════════════════

- USE REAL BUSINESS NAMES exactly as they appear in the review data. Do NOT anonymize.
- Group reviews by business name to build per-competitor profiles.
- Growth potential score: 0-30 = low, 31-60 = moderate, 61-80 = high, 81-100 = exceptional.
- Respond in the same language as the reviews.
- EVERY recommendation MUST cite data: "X yorumun Y tanesinde '{anahtar_kelime}' geçiyor, rakip {rakip_adı}'nda bu konuda {durum} → {önerim}"
- NEVER give generic advice that could apply to any business. Each insight must be SPECIFIC to the analyzed data.
- Output ONLY the JSON. No markdown fences, no extra text."""


# ---------------------------------------------------------------------------
# Comparison Matrix Builder (keyword-based review analysis)
# ---------------------------------------------------------------------------

# Category definitions: Turkish keywords for positive and negative sentiment
REVIEW_CATEGORIES = {
    "Hizmet Hızı": {
        "positive": ["hızlı", "çabuk", "anında", "beklemeden", "hemen geldi", "süper hızlı", "dakikasında"],
        "negative": ["yavaş", "geç geldi", "bekledik", "beklettiler", "uzun sürdü", "gecikmeli", "sipariş gelmedi"],
    },
    "Yemek Kalitesi": {
        "positive": ["lezzetli", "muhteşem", "harika", "taze", "enfes", "nefis", "süper", "mükemmel", "çok güzel", "doyurucu"],
        "negative": ["lezzetsiz", "tatsız", "vasat", "soğuk geldi", "bayat", "kötü", "berbat", "beğenmedim", "tadı yok"],
    },
    "Fiyat Algısı": {
        "positive": ["uygun", "makul", "ucuz", "fiyat performans", "değer", "hesaplı", "bütçe dostu"],
        "negative": ["pahalı", "kazık", "fahiş", "aşırı fiyat", "fiyatı yüksek", "hesap yüksek", "porsiyon küçük"],
    },
    "Personel": {
        "positive": ["ilgili", "güler yüzlü", "nazik", "kibar", "yardımsever", "profesyonel", "samimi", "sıcak"],
        "negative": ["ilgisiz", "kaba", "soğuk", "umursamaz", "saygısız", "suratsız", "lakayt", "müdahale"],
    },
    "Hijyen": {
        "positive": ["temiz", "hijyenik", "steril", "pırıl pırıl", "bakımlı", "düzenli"],
        "negative": ["kirli", "pis", "hijyen", "koku", "toz", "bakımsız", "dezenfekte"],
    },
    "Ortam": {
        "positive": ["şık", "güzel dekor", "rahat", "ferah", "huzurlu", "atmosfer güzel", "manzara", "ambiyans"],
        "negative": ["gürültülü", "karanlık", "havasız", "dar", "sıkışık", "soğuk ortam", "sıcak ortam", "müzik yüksek"],
    },
}


def build_comparison_matrix(reviews: list) -> dict:
    """
    Analyze reviews by business and category using keyword matching.
    Returns a matrix: { business_name: { category: { pos, neg, total, score } } }
    """
    # Group reviews by business
    biz_reviews = {}
    for r in reviews:
        biz = r.get("business", "Unknown")
        if biz not in biz_reviews:
            biz_reviews[biz] = []
        biz_reviews[biz].append(r)

    matrix = {}
    for biz_name, revs in biz_reviews.items():
        if len(revs) < 3:  # skip businesses with too few reviews
            continue
        matrix[biz_name] = {}
        total_revs = len(revs)

        for cat_name, keywords in REVIEW_CATEGORIES.items():
            pos_count = 0
            neg_count = 0

            for r in revs:
                text = (r.get("text") or "").lower()
                if not text:
                    continue
                # Check positive keywords
                if any(kw in text for kw in keywords["positive"]):
                    pos_count += 1
                # Check negative keywords
                if any(kw in text for kw in keywords["negative"]):
                    neg_count += 1

            mentioned = pos_count + neg_count
            if mentioned > 0:
                score = round((pos_count / mentioned) * 5, 1)
            else:
                score = None  # no data for this category

            matrix[biz_name][cat_name] = {
                "positive": pos_count,
                "negative": neg_count,
                "mentioned": mentioned,
                "total_reviews": total_revs,
                "score": score,
            }

    # Sort businesses by total reviews descending
    sorted_matrix = dict(sorted(matrix.items(), key=lambda x: sum(r.get("rating", 0) for r in biz_reviews.get(x[0], [])), reverse=True))

    return {
        "categories": list(REVIEW_CATEGORIES.keys()),
        "businesses": sorted_matrix,
    }


# ---------------------------------------------------------------------------
# Growth Potential Calculator (data-driven, 5-factor formula)
# ---------------------------------------------------------------------------

def calculate_growth_potential(reviews: list, target_url: str | None, competitor_urls: list) -> dict:
    """
    Calculate growth potential score from scraped review data.

    Factors:
    1. Review Quality Score (max 25) - average rating
    2. Review Volume Score (max 20) - volume vs competitors
    3. Trend Score (max 20) - rating trend (recent vs older)
    4. Competitive Advantage Score (max 20) - rating vs competitors
    5. Market Gap Score (max 15) - exploitable competitor weaknesses
    """
    if not reviews:
        return {"score": 50, "breakdown": {}, "summary": "Yeterli veri yok."}

    # Group reviews by business
    biz_reviews = {}
    for r in reviews:
        biz = r.get("business", "Unknown")
        if biz not in biz_reviews:
            biz_reviews[biz] = []
        biz_reviews[biz].append(r)

    # Separate target vs competitor reviews
    all_ratings = [r["rating"] for r in reviews if "rating" in r]
    competitor_reviews = [r for r in reviews if r.get("url") != target_url]
    comp_ratings = [r["rating"] for r in competitor_reviews if "rating" in r]

    # Per-business stats
    biz_stats = {}
    for biz, revs in biz_reviews.items():
        ratings = [r["rating"] for r in revs if "rating" in r]
        if ratings:
            biz_stats[biz] = {
                "avg": sum(ratings) / len(ratings),
                "count": len(ratings),
                "neg_count": sum(1 for rt in ratings if rt <= 2),
            }

    comp_avg_ratings = [s["avg"] for s in biz_stats.values()]
    comp_avg_counts = [s["count"] for s in biz_stats.values()]
    overall_avg_rating = sum(comp_avg_ratings) / len(comp_avg_ratings) if comp_avg_ratings else 3.5
    overall_avg_count = sum(comp_avg_counts) / len(comp_avg_counts) if comp_avg_counts else 10

    # --- Factor 1: Review Quality Score (max 25) ---
    avg_r = overall_avg_rating
    if avg_r >= 4.5:
        quality_score = 25
    elif avg_r >= 4.0:
        quality_score = 20
    elif avg_r >= 3.5:
        quality_score = 15
    elif avg_r >= 3.0:
        quality_score = 10
    else:
        quality_score = 5

    # --- Factor 2: Review Volume Score (max 20) ---
    # More reviews in area = more competitive but also more opportunity
    total_reviews = len(reviews)
    avg_count = overall_avg_count
    if total_reviews > avg_count * len(biz_stats) * 1.2:
        volume_score = 20
    elif total_reviews >= avg_count * len(biz_stats) * 0.8:
        volume_score = 12
    else:
        volume_score = 5

    # --- Factor 3: Trend Score (max 20) ---
    # Since we can't reliably get dates from a single scrape,
    # we estimate based on review position (newer reviews tend to come first)
    if len(comp_ratings) >= 10:
        first_half = comp_ratings[:len(comp_ratings)//2]  # newer
        second_half = comp_ratings[len(comp_ratings)//2:]  # older
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        diff = first_avg - second_avg
        if diff > 0.2:
            trend_score = 20  # improving
        elif diff < -0.2:
            trend_score = 5   # declining
        else:
            trend_score = 12  # stable
    else:
        trend_score = 12  # insufficient data, assume stable

    # --- Factor 4: Competitive Advantage Score (max 20) ---
    # How many competitors have lower ratings = opportunity
    if len(comp_avg_ratings) >= 2:
        median_rating = sorted(comp_avg_ratings)[len(comp_avg_ratings)//2]
        low_rated_competitors = sum(1 for r in comp_avg_ratings if r < 4.0)
        ratio = low_rated_competitors / len(comp_avg_ratings)
        if ratio >= 0.5:
            advantage_score = 20  # many weak competitors
        elif ratio >= 0.2:
            advantage_score = 12  # some weak competitors
        else:
            advantage_score = 5   # all competitors are strong
    else:
        advantage_score = 12

    # --- Factor 5: Market Gap Score (max 15) ---
    # Count negative reviews (1-2 stars) across competitors → exploitable complaints
    total_neg = sum(s["neg_count"] for s in biz_stats.values())
    neg_ratio = total_neg / max(len(reviews), 1)
    if neg_ratio >= 0.15:
        gap_score = 15  # lots of competitor complaints to exploit
    elif neg_ratio >= 0.05:
        gap_score = 8   # some complaints
    else:
        gap_score = 3   # competitors are mostly liked

    total = quality_score + volume_score + trend_score + advantage_score + gap_score

    # Build summary
    labels = {
        "quality": ("Yorum Kalitesi", quality_score, 25),
        "volume": ("Yorum Hacmi", volume_score, 20),
        "trend": ("Trend", trend_score, 20),
        "advantage": ("Rekabet Avantajı", advantage_score, 20),
        "gap": ("Pazar Boşluğu", gap_score, 15),
    }

    strong = [v[0] for v in labels.values() if v[1] >= v[2] * 0.7]
    weak = [v[0] for v in labels.values() if v[1] < v[2] * 0.4]

    if total >= 80:
        level = "Olağanüstü büyüme potansiyeli"
    elif total >= 60:
        level = "Yüksek büyüme potansiyeli"
    elif total >= 40:
        level = "Orta düzey büyüme potansiyeli"
    else:
        level = "Sınırlı büyüme potansiyeli"

    summary_parts = [f"{level} ({total}/100)."]
    if strong:
        summary_parts.append(f"Güçlü alanlar: {', '.join(strong)}.")
    if weak:
        summary_parts.append(f"Geliştirilmesi gereken: {', '.join(weak)}.")
    summary_parts.append(f"Bölgede {len(biz_stats)} rakip analiz edildi, toplam {len(reviews)} yorum incelendi.")

    return {
        "score": total,
        "summary": " ".join(summary_parts),
        "breakdown": {k: {"label": v[0], "score": v[1], "max": v[2]} for k, v in labels.items()},
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root(request: Request):
    """Serve the frontend dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# ---- Stub endpoints the frontend expects ----

@app.get("/api/business")
async def get_business():
    """Frontend checks this on load — no server-side state, return empty."""
    return {"business": None}


class BusinessSetupRequest(BaseModel):
    name: str
    category: str = ""
    country: str = ""
    city: str = ""
    district: str = ""
    maps_url: Optional[str] = None


@app.post("/api/business/setup")
async def business_setup(req: BusinessSetupRequest):
    """Stub: frontend saves business locally, just ack."""
    return {"business_id": 1, "ok": True}


@app.post("/api/business/change")
async def business_change():
    return {"ok": True}


@app.get("/api/dashboard")
async def dashboard():
    return {"error": "no_data", "stats": {}}


@app.get("/api/analysis/latest")
async def analysis_latest():
    return {"analysis": None}


@app.get("/api/analysis/history")
async def analysis_history():
    return {"history": []}


@app.post("/api/cron/trigger")
async def cron_trigger():
    return {"message": "Not implemented in standalone mode."}


# ---- Search endpoint (Playwright scraper) ----

class SearchRequest(BaseModel):
    category: str
    country: str = ""
    city: str
    district: str = ""


@app.post("/search", dependencies=[Depends(verify_bearer_token)])
async def search_businesses(req: SearchRequest):
    """Search Google Maps for businesses using Playwright scraper."""
    logger.info(f"Search request: {req.category} in {req.district}, {req.city}, {req.country}")
    try:
        result = await asyncio.to_thread(
            search_businesses_sync,
            category=req.category,
            city=req.city,
            district=req.district,
            country=req.country,
            max_businesses=30,
        )
        return result
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return {"error": str(e), "businesses": []}


# ---- Analyze endpoint (used by Analysis view) ----

class AnalyzeFromUIRequest(BaseModel):
    category: str = ""
    country: str = ""
    city: str = ""
    district: str = ""
    reviews: str = ""
    target_business_url: Optional[str] = None
    competitor_urls: list[str] = []
    business_id: Optional[int] = None


@app.post("/analyze", dependencies=[Depends(verify_bearer_token)])
async def analyze_from_ui(req: AnalyzeFromUIRequest):
    """Analysis endpoint matching the frontend's expected format."""
    logger.info(f"UI Analyze: {req.category} in {req.district}, {req.city}")

    location_str = req.city
    if req.district:
        location_str = f"{req.district}, {req.city}"
    if req.country:
        location_str = f"{location_str}, {req.country}"

    # If manual reviews provided
    if req.reviews and req.reviews.strip():
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": DASHBOARD_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Business type: {req.category}\nLocation: {location_str}\nMode: competitor_only\n\nReviews:\n{req.reviews}\n\nRespond with ONLY the JSON object."},
                ],
                temperature=0.5,
                max_tokens=4000,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            result_json = json.loads(raw)
            return {
                "result": response.choices[0].message.content,
                "stats": {
                    "mode": "manual",
                    "total_reviews": req.reviews.count("\n") + 1,
                },
                **result_json,
            }
        except Exception as e:
            logger.error(f"Manual analysis failed: {e}")
            return {"error": str(e)}

    # Scraper-based analysis
    if not req.competitor_urls:
        return {"error": "No competitor URLs provided."}

    try:
        scrape_result = await asyncio.to_thread(
            deep_scrape_competitors_sync,
            business_urls=req.competitor_urls,
            target_business_url=req.target_business_url,
            country=req.country,
            min_target_reviews=100,
        )
    except Exception as e:
        logger.error(f"Scrape failed: {e}")
        return {"error": f"Scraping failed: {e}"}

    reviews = scrape_result.get("reviews", [])
    if not reviews:
        return {"error": "No reviews collected from competitors."}

    review_lines = [f"[{r.get('business', 'Unknown')}] ({r['rating']}⭐) {r['text']}" for r in reviews]
    reviews_text = "\n".join(review_lines)

    user_prompt = f"""Business type: {req.category}
Location: {location_str}
Mode: competitor_only

Competitor reviews ({len(reviews)} total):
{reviews_text}

Respond with ONLY the JSON object."""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": DASHBOARD_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=4000,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        result_json = json.loads(raw)
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return {"error": f"AI analysis failed: {e}"}

    # Calculate data-driven growth potential (override AI estimate)
    growth = calculate_growth_potential(reviews, req.target_business_url, req.competitor_urls)
    result_json["growth_potential"] = growth

    # Build data-driven comparison matrix from review keywords
    comp_matrix = build_comparison_matrix(reviews)
    result_json["comparison_matrix"] = comp_matrix

    # Build real competitor profiles from scraped data (override AI anonymization)
    biz_map = {}
    for r in reviews:
        biz_name = r.get("business", "Unknown")
        if biz_name not in biz_map:
            biz_map[biz_name] = {"ratings": [], "texts": []}
        if "rating" in r:
            biz_map[biz_name]["ratings"].append(r["rating"])
        if r.get("text"):
            biz_map[biz_name]["texts"].append(r["text"])

    real_competitors = []
    for biz_name, data in biz_map.items():
        if not data["ratings"]:
            continue
        avg_rating = round(sum(data["ratings"]) / len(data["ratings"]), 1)
        real_competitors.append({
            "name": biz_name,
            "rating": avg_rating,
            "total_reviews": len(data["ratings"]),
        })

    # Sort by review count descending, take top competitors
    real_competitors.sort(key=lambda x: x["total_reviews"], reverse=True)

    # Merge AI-analyzed strengths/weaknesses into real profiles
    ai_competitors = result_json.get("competitors", [])
    ai_by_name = {}
    for ac in ai_competitors:
        ai_by_name[ac.get("name", "").lower().strip()] = ac

    for rc in real_competitors:
        # Try exact match first, then fuzzy
        ai_match = ai_by_name.get(rc["name"].lower().strip())
        if not ai_match:
            # Fuzzy: check if AI name is contained in real name or vice versa
            for ai_name, ai_data in ai_by_name.items():
                if ai_name in rc["name"].lower() or rc["name"].lower() in ai_name:
                    ai_match = ai_data
                    break
        if ai_match:
            rc["strengths"] = ai_match.get("strengths", [])
            rc["weaknesses"] = ai_match.get("weaknesses", [])
        else:
            rc["strengths"] = []
            rc["weaknesses"] = []

    # Override AI's competitor list with real data
    result_json["competitors"] = real_competitors

    return {
        "result": response.choices[0].message.content,
        "stats": {
            "mode": "auto",
            "businesses_analyzed": scrape_result.get("businesses_analyzed", 0),
            "total_reviews": len(reviews),
            "avg_rating": scrape_result.get("avg_rating", 0),
            "competitor_bad_reviews": [r for r in reviews if r["rating"] <= 2][:20],
        },
        **result_json,
    }

@app.get("/api/search-place", response_model=PlaceSearchResponse)
async def search_place(query: str, location: str):
    """
    Search for a business on Google Places using Text Search API.
    query: business name, e.g. "Ahmet Berber Salonu"
    location: location string, e.g. "Karşıyaka, İzmir, Türkiye"
    """
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY not configured")
        return PlaceSearchResponse(results=[])

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={
                    "query": f"{query} {location}",
                    "key": GOOGLE_API_KEY,
                    "language": "tr",
                },
            )
            data = resp.json()
    except Exception as e:
        logger.error(f"Google Places search failed: {e}")
        return PlaceSearchResponse(results=[])

    results: list[PlaceSearchResult] = []
    for place in data.get("results", [])[:5]:
        results.append(
            PlaceSearchResult(
                place_id=place.get("place_id", ""),
                name=place.get("name", ""),
                address=place.get("formatted_address", ""),
                rating=place.get("rating"),
                total_reviews=place.get("user_ratings_total"),
                types=place.get("types", []),
            )
        )

    return PlaceSearchResponse(results=results)


# ---- Find competitors via Places nearbySearch ----

class FindCompetitorsRequest(BaseModel):
    place_id: str
    business_type: str = ""  # e.g. "cafe", "restaurant"
    radius: int = 5000       # meters


@app.post("/api/find-competitors")
async def find_competitors(req: FindCompetitorsRequest):
    """
    1. Get coordinates from place_id
    2. nearbySearch for same business type
    3. Sort by review count, return top 4 with details + reviews
    """
    if not GOOGLE_API_KEY:
        return {"error": "GOOGLE_API_KEY not configured", "competitors": []}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Step 1: Get target business details (coordinates + types)
            details_resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params={
                    "place_id": req.place_id,
                    "fields": "geometry,types,name,rating,user_ratings_total",
                    "key": GOOGLE_API_KEY,
                    "language": "tr",
                },
            )
            details_data = details_resp.json().get("result", {})
            if not details_data.get("geometry"):
                return {"error": "Could not get coordinates for place", "competitors": []}

            lat = details_data["geometry"]["location"]["lat"]
            lng = details_data["geometry"]["location"]["lng"]

            # Determine search type from business_type or place types
            search_type = req.business_type.lower() if req.business_type else ""
            place_types = details_data.get("types", [])
            type_map = {
                "kafe": "cafe", "cafe": "cafe", "kahve": "cafe",
                "restoran": "restaurant", "restaurant": "restaurant",
                "bar": "bar", "lounge": "bar",
                "otel": "lodging", "hotel": "lodging",
                "berber": "hair_care", "kuaför": "hair_care", "güzellik": "beauty_salon",
                "spor": "gym", "diş": "dentist", "eczane": "pharmacy",
            }
            api_type = None
            for key, val in type_map.items():
                if key in search_type:
                    api_type = val
                    break
            if not api_type and place_types:
                api_type = place_types[0]

            # Step 2: Nearby search for competitors
            nearby_params = {
                "location": f"{lat},{lng}",
                "radius": req.radius,
                "key": GOOGLE_API_KEY,
                "language": "tr",
            }
            if api_type:
                nearby_params["type"] = api_type

            nearby_resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params=nearby_params,
            )
            nearby_data = nearby_resp.json()
            places = nearby_data.get("results", [])

            # Remove self, sort by review count
            places = [p for p in places if p.get("place_id") != req.place_id]
            places.sort(key=lambda x: x.get("user_ratings_total", 0), reverse=True)
            top_competitors = places[:4]

            # Step 3: Get details + reviews for each competitor
            competitors = []
            for comp in top_competitors:
                comp_detail_resp = await client.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": comp["place_id"],
                        "fields": "name,rating,reviews,user_ratings_total,formatted_address,photos",
                        "key": GOOGLE_API_KEY,
                        "language": "tr",
                    },
                )
                comp_detail = comp_detail_resp.json().get("result", {})

                # Extract reviews
                reviews = []
                for rev in comp_detail.get("reviews", []):
                    reviews.append({
                        "rating": rev.get("rating", 0),
                        "text": rev.get("text", ""),
                        "time": rev.get("relative_time_description", ""),
                        "author": rev.get("author_name", ""),
                    })

                # Photo URL (first photo if available)
                photo_ref = None
                photos = comp_detail.get("photos", [])
                if photos:
                    photo_ref = photos[0].get("photo_reference")

                competitors.append({
                    "place_id": comp["place_id"],
                    "name": comp_detail.get("name", comp.get("name", "")),
                    "rating": comp_detail.get("rating", comp.get("rating")),
                    "total_reviews": comp_detail.get("user_ratings_total", comp.get("user_ratings_total", 0)),
                    "address": comp_detail.get("formatted_address", ""),
                    "reviews": reviews,
                    "photo_url": f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={photo_ref}&key={GOOGLE_API_KEY}" if photo_ref else None,
                })

            # Also return target business info
            target = {
                "name": details_data.get("name", ""),
                "rating": details_data.get("rating"),
                "total_reviews": details_data.get("user_ratings_total", 0),
            }

            logger.info(f"Found {len(competitors)} competitors near {target['name']}")

            return {
                "target": target,
                "competitors": competitors,
                "search_info": {
                    "lat": lat,
                    "lng": lng,
                    "radius": req.radius,
                    "type": api_type,
                    "total_found": len(places),
                },
            }

    except Exception as e:
        logger.error(f"Find competitors failed: {e}")
        return {"error": str(e), "competitors": []}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """
    Main analysis endpoint.
    1. Parse location
    2. Search competitors on Google Maps
    3. Try to find target business
    4. Deep scrape reviews
    5. AI analysis → structured JSON
    """
    logger.info(f"Analyze request: business={req.business_name}, location={req.location}, type={req.business_type}")

    loc = parse_location(req.location)
    city = loc["city"]
    district = loc["district"]
    country = loc["country"]

    if not city:
        raise HTTPException(status_code=400, detail="Could not parse city from location")

    # Step 1: Search for businesses in the area
    logger.info(f"Searching businesses: {req.business_type} in {district}, {city}, {country}")
    search_result = await asyncio.to_thread(
        search_businesses_sync,
        category=req.business_type,
        city=city,
        district=district,
        country=country,
        max_businesses=30,
    )

    if search_result.get("error") and not search_result.get("businesses"):
        raise HTTPException(status_code=502, detail=f"Scraping failed: {search_result['error']}")

    businesses = search_result.get("businesses", [])
    if not businesses:
        raise HTTPException(status_code=404, detail=f"No {req.business_type} businesses found in {req.location}")

    # Step 2: Find the target business by name match
    target_url = None
    competitor_urls = []
    target_name_lower = req.business_name.strip().lower()

    # If found_on_maps=False, skip target matching entirely
    if req.found_on_maps is False:
        target_url = None
        competitor_urls = [b["url"] for b in businesses]
        competitor_only_mode = True
        logger.info(f"found_on_maps=False → competitor_only mode for '{req.business_name}'")
    else:
        for biz in businesses:
            biz_name_lower = biz.get("name", "").strip().lower()
            if target_name_lower in biz_name_lower or biz_name_lower in target_name_lower:
                target_url = biz["url"]
                logger.info(f"Target business matched: {biz['name']}")
            else:
                competitor_urls.append(biz["url"])

        # If target not found, all are competitors (competitor_only_mode)
        competitor_only_mode = target_url is None
        if competitor_only_mode:
            competitor_urls = [b["url"] for b in businesses]
            logger.warning(f"Target business '{req.business_name}' not found on Maps. Using competitor_only mode.")

    if not competitor_urls:
        raise HTTPException(status_code=404, detail="No competitors found for analysis")

    # Step 3: Deep scrape reviews
    logger.info(f"Deep scraping {len(competitor_urls)} competitors (target={'found' if not competitor_only_mode else 'not found'})")
    scrape_result = await asyncio.to_thread(
        deep_scrape_competitors_sync,
        business_urls=competitor_urls,
        target_business_url=target_url if not competitor_only_mode else None,
        country=country,
        min_target_reviews=200,
    )

    if scrape_result.get("error") and not scrape_result.get("reviews"):
        raise HTTPException(status_code=502, detail=f"Review scraping failed: {scrape_result['error']}")

    reviews = scrape_result.get("reviews", [])
    target_reviews = scrape_result.get("target_reviews", [])

    if not reviews:
        raise HTTPException(status_code=404, detail="No reviews collected from competitors")

    # Step 4: Build AI prompt
    review_lines = [f"[{r.get('business', 'Unknown')}] ({r['rating']}⭐) {r['text']}" for r in reviews]
    reviews_text = "\n".join(review_lines)

    location_str = city
    if district:
        location_str = f"{district}, {city}"
    if country:
        location_str = f"{location_str}, {country}"

    user_prompt = f"""Business type: {req.business_type}
Target business name: {req.business_name}
Location: {location_str}
Mode: {"competitor_only" if competitor_only_mode else "full_comparison"}

Competitor reviews ({len(reviews)} total):
{reviews_text}
"""

    if target_reviews and not competitor_only_mode:
        target_lines = [f"({r['rating']}⭐) {r['text']}" for r in target_reviews]
        user_prompt += f"\n--- TARGET BUSINESS REVIEWS ({len(target_reviews)} reviews) ---\n"
        user_prompt += "\n".join(target_lines)

    user_prompt += "\n\nRespond with ONLY the JSON object."

    # Step 5: Call OpenAI
    logger.info("Calling OpenAI for structured analysis...")
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": DASHBOARD_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=4000,
        )
        raw_text = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)}")

    # Step 6: Parse JSON response
    try:
        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]  # remove first line
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}\nRaw: {raw_text[:500]}")
        raise HTTPException(status_code=502, detail="AI returned invalid JSON. Please retry.")

    # Step 7: Validate and return
    try:
        validated = AnalyzeResponse(**result)
    except Exception as e:
        logger.error(f"Response validation failed: {e}")
        # Try to fix common issues and return best-effort
        raise HTTPException(status_code=502, detail=f"AI response schema mismatch: {str(e)}")

    return validated


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    logger.info(f"Starting Review Analyzer API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

