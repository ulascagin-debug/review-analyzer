"""
Review Analyzer — Main Flask Application
Full dashboard backend with business setup, automated scraping, AI analysis, and data API.
"""

import os
import json
import logging
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
from scraper import search_businesses_sync, deep_scrape_competitors_sync
from auth import require_auth, generate_token
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from database import (
    init_db, save_business, get_active_business, deactivate_business,
    save_competitors, get_competitors, save_reviews, get_reviews,
    get_bad_competitor_reviews, get_review_stats, save_analysis,
    get_latest_analysis, get_analysis_history, get_cron_logs
)
from analyzer import process_reviews_batch, compute_sentiment_score, detect_opportunities
from scheduler import start_scheduler, run_scrape_now

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app")

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------
app = Flask(__name__)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60/minute"],
    storage_uri="memory://",
)

# Initialize DB on startup
init_db()
logger.info("Database initialized.")

# Start scheduler
try:
    start_scheduler()
except Exception as e:
    logger.warning(f"Scheduler start failed (non-fatal): {e}")

# ---------------------------------------------------------------------------
# API Key Protection
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.before_request
def check_api_key():
    # Exempt public routes from auth
    public_paths = ["/health", "/", "/token"]
    if request.path in public_paths or request.path.startswith("/static"):
        return None

    # Allow same-origin requests (frontend served from this server)
    referer = request.headers.get("Referer", "")
    origin = request.headers.get("Origin", "")
    host = request.host_url.rstrip("/")
    if referer.startswith(host) or origin.startswith(host):
        return None

    secret = os.environ.get("ANALYZER_SECRET_KEY")
    if not secret:
        # No key configured → skip check
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid Authorization header."}), 401

    token = auth_header[7:]
    if token != secret:
        return jsonify({"error": "Invalid API key."}), 401

    return None

# ---------------------------------------------------------------------------
# AI Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Sen, spesifik iş kolunda 20 yıllık saha tecrübesine sahip, acımasız, aşırı zeki ve vizyoner bir Danışmansın. 
Görevin: Spesifik bir lokasyondaki rakip işletmelerin müşteri yorumlarını analiz edip, kimsenin aklına gelmeyecek, sığ olmayan, inanılmaz derecede yaratıcı ve doğrudan ciro/müşteri sadakati getirecek sıra dışı taktikler üretmektir.

TEMEL PRENSİPLER (ÇOK KRİTİK):
- Rakip işletme isimlerini ASLA açık etme.
- Sadece analiz edilen spesifik sektöre ait uzman terminolojisi kullan.
- "Güleryüzlü olun, fiyatı indirin, temizliği artırın" gibi HERKESİN bileceği ucuz tavsiyeleri KESİNLİKLE verme.
- Müşteri psikolojisini ve şikayetlerdeki gizli kalmış (satır arası) isyanları tespit et.
- Fikirlerin olağanüstü, uygulanabilir ve lokasyona özel olmalı.
- Her öneriyi VERİYE dayandır, yorum numarası ve tarihi ile referans ver.
- SOMUT, ÖLÇÜLEBİLİR aksiyonlar sun.

ÇIKTI FORMATI (KATI FORMAT - Markdown kullan):

## 📋 GİZLİ KALMIŞ SEKTÖREL YARALAR TABLOSU
| Rakip Zafiyeti | Müşterinin Gerçekten Hissettiği | Senin Vurucu Hamlen |
|-------|--------|---------------|
(En sık görülen 5 ölümcül problemi ve ona karşı yapılabilecek en zekice hamleyi listele)

## 1. 📊 LOKAL PAZARIN RÖNTGENİ
- Sektör uzmanı gözüyle buradaki müşterinin profil analizi ve asıl aradığı şey.

## 2. ⚡ GÜÇ/ZAAF VE REKABET (GAP) ANALİZİ
- "Senin İşletmen" ile "Rakiplerin" arasındaki temel farklar.

## 3. 💡 KİMSENİN AKLINA GELMEYECEK 3 UZMAN FİKRİ
- Ezber bozan taktikler.

## 4. 🚀 AŞIRI KAZANÇLI LOKAL KAMPANYALAR
- O bölgeye özel tasarlanmış 2 spesifik kampanya.

## 5. 📢 BEYNE İŞLEYEN REKLAM METİNLERİ
- 2 vurucu reklam kopyası.

## 6. 🤖 CHATBOT MESAJLARI
- 2 hipnotik mesaj şablonu.

DİL: %100 TÜRKÇE.
TON: Sektör kurdu, sarsıcı, yaratıcı ve zeka fışkıran bir tarz.
"""

TIMEFRAME_PROMPT = """
Ayrıca, analizinin sonuna aşağıdaki zaman dilimlerine özel TAKTİKSEL TAVSİYELER ekle:

## ⏱️ ZAMAN DİLİMİNE GÖRE AKSİYON PLANI

### 📅 1 HAFTALIK (Acil Müdahale)
- Bu hafta içinde hemen uygulanabilecek 2-3 hızlı kazanım (quick wins). Sıfır veya düşük maliyetli, anında etki yaratacak aksiyonlar.
- Her aksiyon için NEDEN ve NASIL detaylarını ver.

### 📅 1 AYLIK (Kısa Vadeli Büyüme)  
- 1 ay içinde uygulanacak 2-3 orta ölçekli strateji. Operasyonel iyileştirmeler, kampanya lansmanları, müşteri deneyimi değişiklikleri.
- Beklenen etki ve KPI'ları belirt.

### 📅 3 AYLIK (Orta Vadeli Strateji)
- 3 ay içinde rakipleri geçecek 2-3 sistematik hamle. Süreç optimizasyonu, marka farklılaştırma, sadakat programı.
- Hedef metrikleri ve milestones tanımla.

### 📅 6 AYLIK (Büyüme Yol Haritası)
- 6 aylık büyüme projeksiyonu. Pazar payı hedefi, gelir artışı tahmini, genişleme planı.
- Yatırım-getiri analizi yap.

### 📅 1 YILLIK (Vizyon Planı)
- 1 yıl içinde rakipleri tamamen geride bırakacak 2-3 büyük vizyon hamlesi.
- Marka konumlandırma, pazar hakimiyeti stratejisi, uzun vadeli sadakat sistemi.
- Somut rakamsal hedefler ver.
"""


# ---------------------------------------------------------------------------
# Page Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route("/token", methods=["POST"])
@limiter.limit("5/minute")
def get_token():
    data = request.get_json() or {}
    client_id = data.get("client_id", "anonymous")
    token = generate_token({"client_id": client_id})
    return jsonify({"token": token})


# ---------------------------------------------------------------------------
# Business Setup API
# ---------------------------------------------------------------------------

@app.route("/api/business", methods=["GET"])
def get_business():
    """Get the currently active business."""
    biz = get_active_business()
    if biz:
        return jsonify({"business": biz})
    return jsonify({"business": None})


@app.route("/api/business/setup", methods=["POST"])
@limiter.limit("10/minute")
def setup_business():
    """Save a new business (from Google Places or manual entry)."""
    data = request.get_json()
    name = data.get("name", "").strip()
    category = data.get("category", "").strip()
    city = data.get("city", "").strip()

    if not name or not category or not city:
        return jsonify({"error": "name, category, and city are required."}), 400

    business_id = save_business(
        name=name,
        category=category,
        city=city,
        country=data.get("country", ""),
        district=data.get("district", ""),
        place_id=data.get("place_id"),
        address=data.get("address"),
        rating=data.get("rating", 0),
        total_reviews=data.get("total_reviews", 0),
        maps_url=data.get("maps_url"),
    )

    logger.info(f"Business setup: {name} (ID: {business_id})")
    return jsonify({"business_id": business_id, "message": "Business saved."})


@app.route("/api/business/change", methods=["POST"])
def change_business():
    """Deactivate current business so user can set up a new one."""
    deactivate_business()
    return jsonify({"message": "Business deactivated. Set up a new one."})


# ---------------------------------------------------------------------------
# Search & Scrape
# ---------------------------------------------------------------------------

@app.route("/search", methods=["POST"])
@limiter.limit("10/minute")
def search():
    """Step 1: Search for businesses in the area."""
    try:
        data = request.get_json()
        category = data.get("category", "").strip()
        country = data.get("country", "").strip()
        city = data.get("city", "").strip()
        district = data.get("district", "").strip()

        if not category or not city:
            return jsonify({"error": "Category and city are required."}), 400

        logger.info(f"Searching: category='{category}', city='{city}', district='{district}', country='{country}'")

        result = search_businesses_sync(category, city, district, country, max_businesses=150)

        if result.get("error"):
            logger.error(f"Scraper returned error: {result['error']}")
            if not result.get("businesses"):
                return jsonify({"error": f"Arama hatası: {result['error']}"}), 500

        if not result.get("businesses"):
            logger.warning(f"No businesses found for '{category}' in {city}")
            return jsonify({"error": f"'{category}' için {city} bölgesinde işletme bulunamadı."}), 404

        logger.info(f"Found {len(result['businesses'])} businesses")

        # Save competitors if we have an active business
        biz = get_active_business()
        if biz:
            save_competitors(biz["id"], result["businesses"])

        return jsonify({"businesses": result["businesses"]})

    except Exception as e:
        logger.error(f"Search endpoint error: {e}", exc_info=True)
        return jsonify({"error": f"Sunucu hatası: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@app.route("/analyze", methods=["POST"])
@limiter.limit("5/minute")
def analyze():
    """Full analysis: scrape + AI analysis with multi-timeframe plans."""
    try:
        data = request.get_json()
        category = data.get("category", "").strip()
        country = data.get("country", "").strip()
        city = data.get("city", "").strip()
        district = data.get("district", "").strip()
        business_id = data.get("business_id", None)
        manual_reviews = data.get("reviews", "").strip()
        competitor_urls = data.get("competitor_urls", [])
        target_business_url = data.get("target_business_url", None)

        if not category or not city:
            return jsonify({"error": "Category and city are required."}), 400

        competitor_only_mode = not target_business_url or target_business_url.strip() == ""

        if not manual_reviews:
            if not competitor_urls:
                return jsonify({"error": "No competitors provided for analysis."}), 400

            scrape_result = deep_scrape_competitors_sync(
                business_urls=competitor_urls,
                target_business_url=target_business_url if not competitor_only_mode else None,
                country=country,
                min_target_reviews=200,
            )

            if scrape_result.get("error") and not scrape_result.get("reviews"):
                return jsonify({"error": f"Scraping error: {scrape_result['error']}"}), 500

            if not scrape_result.get("reviews"):
                return jsonify({"error": "Failed to collect reviews from the competitors."}), 404

            # Process reviews with sentiment analysis
            raw_reviews = scrape_result["reviews"]
            processed_reviews = process_reviews_batch(raw_reviews, category)

            target_raw = scrape_result.get("target_reviews", [])
            processed_target = process_reviews_batch(target_raw, category) if target_raw else []

            # Save to DB if we have a business
            active_biz = get_active_business()
            if active_biz:
                save_reviews(active_biz["id"], processed_reviews, source="competitor")
                if processed_target:
                    save_reviews(active_biz["id"], processed_target, source="own")

            # Format for AI
            review_lines = [f"({r['rating']}⭐) {r['text']}" for r in processed_reviews]
            reviews_text = "\n".join(review_lines)

            competitor_bad_reviews = [
                {"rating": r["rating"], "text": r["text"][:150], "business": r.get("business", ""),
                 "sentiment": r.get("sentiment", ""), "keywords": r.get("keywords", [])}
                for r in processed_reviews if r["rating"] <= 3 and 15 <= len(r["text"]) <= 150
            ]
            competitor_bad_reviews.sort(key=lambda x: x["rating"])

            target_good_reviews = [
                {"rating": r["rating"], "text": r["text"][:150], "business": r.get("business", "")}
                for r in processed_target if r["rating"] >= 4 and 15 <= len(r["text"]) <= 150
            ]
            target_good_reviews.sort(key=lambda x: x["rating"], reverse=True)

            target_review_lines = [f"({r['rating']}⭐) {r['text']}" for r in processed_target]
            target_reviews_text = "\n".join(target_review_lines)

            # Compute sentiment stats
            sentiment_score = compute_sentiment_score(processed_reviews)
            opportunities = detect_opportunities(
                [r for r in processed_reviews if r["rating"] <= 2]
            )

            stats = {
                "businesses_analyzed": scrape_result.get("businesses_analyzed", len(competitor_urls)),
                "total_reviews": scrape_result["total_reviews"],
                "avg_rating": scrape_result["avg_rating"],
                "mode": "competitor_only" if competitor_only_mode else "auto",
                "competitor_only_mode": competitor_only_mode,
                "competitor_bad_reviews": competitor_bad_reviews[:20],
                "target_good_reviews": target_good_reviews[:10],
                "sentiment_score": sentiment_score,
                "opportunities": opportunities[:5],
            }

        else:
            # Manual mode
            reviews_text = manual_reviews
            target_reviews_text = ""
            review_count = len([l for l in manual_reviews.split("\n") if l.strip()])
            stats = {
                "businesses_analyzed": "N/A",
                "total_reviews": review_count,
                "avg_rating": "N/A",
                "mode": "manual",
                "competitor_only_mode": True,
                "sentiment_score": 50,
            }

        # AI Analysis
        location_str = city
        if district:
            location_str = f"{district}, {city}"
        if country:
            location_str = f"{location_str}, {country}"

        full_system_prompt = SYSTEM_PROMPT + TIMEFRAME_PROMPT

        if competitor_only_mode:
            mode_note = "\n⚠️ NOT: Hedef işletme Google Maps'te bulunamadı. Sadece rakip verileri üzerinden analiz yap.\n"
        else:
            mode_note = ""

        user_prompt = f"""Business category: {category}

Location: {location_str}
{mode_note}
Analyze the following aggregated competitor reviews ({stats['total_reviews']} reviews):

{reviews_text}
"""
        if target_reviews_text and not competitor_only_mode:
            user_prompt += f"\n\n--- HEDEF İŞLETMENİN YORUMLARI ---\n{target_reviews_text}\n"

        user_prompt += "\nGenerate a full local competitive analysis and strategy."

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=8000,
        )

        result_text = response.choices[0].message.content

        # Save analysis to DB
        active_biz = get_active_business()
        if active_biz:
            save_analysis(
                active_biz["id"], result_text,
                stats_json=stats,
                competitor_bad=stats.get("competitor_bad_reviews", []),
                target_good=stats.get("target_good_reviews", []),
            )

        response_data = {
            "result": result_text,
            "stats": stats,
            "competitor_only_mode": competitor_only_mode,
        }

        if business_id:
            response_data["business_id"] = business_id

        response_data["timeframe"] = {
            "1_week": "Acil müdahale aksiyonları",
            "1_month": "Kısa vadeli büyüme stratejisi",
            "3_months": "Orta vadeli strateji",
            "6_months": "Büyüme yol haritası",
            "1_year": "Uzun vadeli vizyon planı",
        }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------

@app.route("/api/dashboard", methods=["GET"])
def dashboard_data():
    """Get dashboard data: stats, trends, charts, opportunities."""
    biz = get_active_business()
    if not biz:
        return jsonify({"error": "No active business"}), 404

    days = int(request.args.get("days", 30))
    stats = get_review_stats(biz["id"], days=days)

    # Get latest analysis
    latest = get_latest_analysis(biz["id"])

    # Get bad competitor reviews for pop-ups
    bad_reviews = get_bad_competitor_reviews(biz["id"], limit=30)

    # Get opportunities from bad reviews
    all_bad = get_reviews(biz["id"], source="competitor", limit=500)
    bad_for_opps = [r for r in all_bad if r.get("rating", 5) <= 2]
    opportunities = detect_opportunities(bad_for_opps, min_count=2)

    return jsonify({
        "business": biz,
        "stats": stats,
        "latest_analysis": {
            "id": latest["id"] if latest else None,
            "created_at": latest["created_at"] if latest else None,
            "has_data": latest is not None,
        },
        "bad_competitor_reviews": bad_reviews[:20],
        "opportunities": opportunities[:8],
    })


@app.route("/api/reviews/bad-competitors", methods=["GET"])
def bad_competitor_reviews():
    """Get recent bad competitor reviews for pop-up notifications."""
    biz = get_active_business()
    if not biz:
        return jsonify({"reviews": []})

    reviews = get_bad_competitor_reviews(biz["id"], limit=30)
    return jsonify({"reviews": reviews})


@app.route("/api/analysis/history", methods=["GET"])
def analysis_history():
    """Get past analysis history."""
    biz = get_active_business()
    if not biz:
        return jsonify({"history": []})

    history = get_analysis_history(biz["id"], limit=10)
    return jsonify({"history": history})


@app.route("/api/analysis/latest", methods=["GET"])
def latest_analysis():
    """Get the most recent full analysis."""
    biz = get_active_business()
    if not biz:
        return jsonify({"analysis": None})

    latest = get_latest_analysis(biz["id"])
    return jsonify({"analysis": latest})


@app.route("/api/cron/logs", methods=["GET"])
def cron_logs():
    """Get cron job history."""
    biz = get_active_business()
    logs = get_cron_logs(biz["id"] if biz else None, limit=20)
    return jsonify({"logs": logs})


@app.route("/api/cron/trigger", methods=["POST"])
@limiter.limit("2/minute")
def trigger_cron():
    """Manually trigger a data collection run."""
    try:
        import threading
        thread = threading.Thread(target=run_scrape_now, daemon=True)
        thread.start()
        return jsonify({"message": "Scrape job triggered in background."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    """Export reviews as CSV."""
    biz = get_active_business()
    if not biz:
        return jsonify({"error": "No active business"}), 404

    reviews = get_reviews(biz["id"], limit=5000)

    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Rating", "Text", "Sentiment", "Keywords", "Source", "Business", "Date"])
    for r in reviews:
        writer.writerow([
            r.get("rating", ""),
            r.get("text", ""),
            r.get("sentiment", ""),
            r.get("keywords", ""),
            r.get("source", ""),
            r.get("business_name", ""),
            r.get("scraped_at", ""),
        ])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=reviews_{biz['name']}.csv"}
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False)
