"""
Database layer for Review Analyzer.
SQLite-based persistent storage for businesses, reviews, competitors, and analyses.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "review_analyzer.db")


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                place_id TEXT,
                address TEXT,
                category TEXT NOT NULL,
                country TEXT DEFAULT '',
                city TEXT NOT NULL,
                district TEXT DEFAULT '',
                rating REAL DEFAULT 0,
                total_reviews INTEGER DEFAULT 0,
                maps_url TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS competitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                rating REAL DEFAULT 0,
                total_reviews INTEGER DEFAULT 0,
                last_scraped TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                competitor_id INTEGER,
                source TEXT DEFAULT 'competitor',
                text TEXT NOT NULL,
                rating INTEGER DEFAULT 0,
                sentiment TEXT DEFAULT 'neutral',
                keywords TEXT DEFAULT '[]',
                business_name TEXT DEFAULT '',
                scraped_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
                FOREIGN KEY (competitor_id) REFERENCES competitors(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                analysis_type TEXT DEFAULT 'full',
                result_md TEXT,
                result_json TEXT,
                stats_json TEXT,
                competitor_bad_reviews TEXT DEFAULT '[]',
                target_good_reviews TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS cron_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER,
                job_type TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                reviews_collected INTEGER DEFAULT 0,
                competitors_scraped INTEGER DEFAULT 0,
                error_msg TEXT,
                started_at TEXT DEFAULT (datetime('now')),
                finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_reviews_business ON reviews(business_id);
            CREATE INDEX IF NOT EXISTS idx_reviews_scraped ON reviews(scraped_at);
            CREATE INDEX IF NOT EXISTS idx_reviews_sentiment ON reviews(sentiment);
            CREATE INDEX IF NOT EXISTS idx_competitors_business ON competitors(business_id);
            CREATE INDEX IF NOT EXISTS idx_analysis_business ON analysis_history(business_id);
        """)


# ── Business CRUD ──────────────────────────────────────────────

def save_business(name, category, city, country="", district="",
                  place_id=None, address=None, rating=0, total_reviews=0, maps_url=None):
    """Save or update the active business. Deactivates previous."""
    with get_db() as conn:
        # Deactivate all existing
        conn.execute("UPDATE businesses SET is_active = 0")
        # Insert new
        conn.execute("""
            INSERT INTO businesses (name, place_id, address, category, country, city, district,
                                    rating, total_reviews, maps_url, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (name, place_id, address, category, country, city, district,
              rating, total_reviews, maps_url))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_active_business():
    """Get currently active business."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM businesses WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def deactivate_business():
    """Deactivate current business."""
    with get_db() as conn:
        conn.execute("UPDATE businesses SET is_active = 0")


# ── Competitors ────────────────────────────────────────────────

def save_competitors(business_id, competitors_list):
    """Save competitor list for a business. competitors_list: [{name, url, rating?}]"""
    with get_db() as conn:
        for comp in competitors_list:
            conn.execute("""
                INSERT OR IGNORE INTO competitors (business_id, name, url, rating)
                VALUES (?, ?, ?, ?)
            """, (business_id, comp.get("name", ""), comp["url"], comp.get("rating", 0)))


def get_competitors(business_id):
    """Get all competitors for a business."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM competitors WHERE business_id = ? ORDER BY rating DESC", (business_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_competitor_scraped(competitor_id):
    """Mark competitor as recently scraped."""
    with get_db() as conn:
        conn.execute(
            "UPDATE competitors SET last_scraped = datetime('now') WHERE id = ?", (competitor_id,)
        )


# ── Reviews ────────────────────────────────────────────────────

def save_reviews(business_id, reviews_list, source="competitor", competitor_id=None):
    """Save reviews, deduplicating by text hash."""
    saved = 0
    with get_db() as conn:
        existing = set()
        rows = conn.execute(
            "SELECT text FROM reviews WHERE business_id = ?", (business_id,)
        ).fetchall()
        for r in rows:
            existing.add(r["text"].strip().lower())

        for rev in reviews_list:
            text = rev.get("text", "").strip()
            if not text or text.lower() in existing:
                continue
            existing.add(text.lower())
            conn.execute("""
                INSERT INTO reviews (business_id, competitor_id, source, text, rating,
                                     sentiment, keywords, business_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                business_id, competitor_id, source, text,
                rev.get("rating", 0),
                rev.get("sentiment", "neutral"),
                json.dumps(rev.get("keywords", []), ensure_ascii=False),
                rev.get("business", "")
            ))
            saved += 1
    return saved


def get_reviews(business_id, source=None, days=None, limit=None):
    """Get reviews with optional filters."""
    with get_db() as conn:
        query = "SELECT * FROM reviews WHERE business_id = ?"
        params = [business_id]

        if source:
            query += " AND source = ?"
            params.append(source)
        if days:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            query += " AND scraped_at >= ?"
            params.append(cutoff)

        query += " ORDER BY scraped_at DESC"
        if limit:
            query += f" LIMIT {int(limit)}"

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_bad_competitor_reviews(business_id, max_rating=2, limit=50):
    """Get bad competitor reviews for pop-up alerts."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM reviews
            WHERE business_id = ? AND source = 'competitor' AND rating <= ?
            AND length(text) >= 15 AND length(text) <= 200
            ORDER BY scraped_at DESC LIMIT ?
        """, (business_id, max_rating, limit)).fetchall()
        return [dict(r) for r in rows]


def get_review_stats(business_id, days=30):
    """Get aggregated review statistics."""
    with get_db() as conn:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        total = conn.execute(
            "SELECT COUNT(*) as c FROM reviews WHERE business_id = ?", (business_id,)
        ).fetchone()["c"]

        recent = conn.execute(
            "SELECT COUNT(*) as c FROM reviews WHERE business_id = ? AND scraped_at >= ?",
            (business_id, cutoff)
        ).fetchone()["c"]

        avg_rating = conn.execute(
            "SELECT AVG(rating) as a FROM reviews WHERE business_id = ? AND rating > 0",
            (business_id,)
        ).fetchone()["a"] or 0

        sentiment_counts = {}
        for sent in ["positive", "negative", "neutral"]:
            sentiment_counts[sent] = conn.execute(
                "SELECT COUNT(*) as c FROM reviews WHERE business_id = ? AND sentiment = ?",
                (business_id, sent)
            ).fetchone()["c"]

        # Daily sentiment trend
        trend_rows = conn.execute("""
            SELECT date(scraped_at) as day,
                   SUM(CASE WHEN sentiment='positive' THEN 1 ELSE 0 END) as pos,
                   SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) as neg,
                   SUM(CASE WHEN sentiment='neutral' THEN 1 ELSE 0 END) as neu,
                   COUNT(*) as total,
                   AVG(rating) as avg_r
            FROM reviews WHERE business_id = ? AND scraped_at >= ?
            GROUP BY date(scraped_at) ORDER BY day
        """, (business_id, cutoff)).fetchall()

        # Keyword frequency
        all_keywords = []
        kw_rows = conn.execute(
            "SELECT keywords FROM reviews WHERE business_id = ? AND keywords != '[]'",
            (business_id,)
        ).fetchall()
        for r in kw_rows:
            try:
                kws = json.loads(r["keywords"])
                all_keywords.extend(kws)
            except:
                pass

        keyword_freq = {}
        for kw in all_keywords:
            keyword_freq[kw] = keyword_freq.get(kw, 0) + 1
        top_keywords = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)[:15]

        return {
            "total_reviews": total,
            "recent_reviews": recent,
            "avg_rating": round(avg_rating, 1),
            "sentiment": sentiment_counts,
            "daily_trend": [dict(r) for r in trend_rows],
            "top_keywords": top_keywords,
        }


# ── Analysis History ───────────────────────────────────────────

def save_analysis(business_id, result_md, result_json=None, stats_json=None,
                  competitor_bad=None, target_good=None, analysis_type="full"):
    """Save an analysis result."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO analysis_history (business_id, analysis_type, result_md, result_json,
                                          stats_json, competitor_bad_reviews, target_good_reviews)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            business_id, analysis_type, result_md,
            json.dumps(result_json or {}, ensure_ascii=False),
            json.dumps(stats_json or {}, ensure_ascii=False),
            json.dumps(competitor_bad or [], ensure_ascii=False),
            json.dumps(target_good or [], ensure_ascii=False),
        ))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_latest_analysis(business_id):
    """Get the most recent analysis."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM analysis_history
            WHERE business_id = ? ORDER BY created_at DESC LIMIT 1
        """, (business_id,)).fetchone()
        if row:
            d = dict(row)
            d["result_json"] = json.loads(d.get("result_json") or "{}")
            d["stats_json"] = json.loads(d.get("stats_json") or "{}")
            d["competitor_bad_reviews"] = json.loads(d.get("competitor_bad_reviews") or "[]")
            d["target_good_reviews"] = json.loads(d.get("target_good_reviews") or "[]")
            return d
        return None


def get_analysis_history(business_id, limit=10):
    """Get recent analysis history."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, business_id, analysis_type, stats_json, created_at
            FROM analysis_history WHERE business_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (business_id, limit)).fetchall()
        return [dict(r) for r in rows]


# ── Cron Logs ──────────────────────────────────────────────────

def log_cron_start(business_id, job_type="scrape"):
    """Log start of a cron job."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO cron_logs (business_id, job_type, status)
            VALUES (?, ?, 'running')
        """, (business_id, job_type))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def log_cron_end(log_id, status="success", reviews_collected=0, competitors_scraped=0, error_msg=None):
    """Log end of a cron job."""
    with get_db() as conn:
        conn.execute("""
            UPDATE cron_logs SET status = ?, reviews_collected = ?,
                                 competitors_scraped = ?, error_msg = ?,
                                 finished_at = datetime('now')
            WHERE id = ?
        """, (status, reviews_collected, competitors_scraped, error_msg, log_id))


def get_cron_logs(business_id=None, limit=20):
    """Get recent cron logs."""
    with get_db() as conn:
        if business_id:
            rows = conn.execute("""
                SELECT * FROM cron_logs WHERE business_id = ?
                ORDER BY started_at DESC LIMIT ?
            """, (business_id, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cron_logs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
