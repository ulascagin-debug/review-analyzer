"""
Scheduler for automated daily review collection.
Uses APScheduler to run data collection at 08:00, 14:00, 22:00 daily.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import get_active_business, get_competitors, save_reviews, log_cron_start, log_cron_end
from analyzer import process_reviews_batch

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler(daemon=True)


def collect_reviews_job():
    """
    Daily review collection job:
    1. Get active business
    2. Scrape competitor reviews
    3. Run sentiment + keyword analysis
    4. Save to DB
    """
    business = get_active_business()
    if not business:
        logger.info("No active business configured. Skipping cron job.")
        return

    business_id = business["id"]
    log_id = log_cron_start(business_id, "scrape")
    logger.info(f"Starting cron scrape for business: {business['name']} (ID: {business_id})")

    try:
        from scraper import deep_scrape_competitors_sync
        
        competitors = get_competitors(business_id)
        if not competitors:
            log_cron_end(log_id, "skipped", error_msg="No competitors found")
            logger.warning("No competitors found for scraping.")
            return

        # Scrape top 20 competitors
        comp_urls = [c["url"] for c in competitors[:20]]
        
        scrape_result = deep_scrape_competitors_sync(
            business_urls=comp_urls,
            target_business_url=business.get("maps_url"),
            country=business.get("country", ""),
            min_target_reviews=100,
        )

        if scrape_result.get("error") and not scrape_result.get("reviews"):
            log_cron_end(log_id, "error", error_msg=scrape_result["error"])
            logger.error(f"Scraping failed: {scrape_result['error']}")
            return

        reviews = scrape_result.get("reviews", [])
        target_reviews = scrape_result.get("target_reviews", [])

        # Process with sentiment analysis
        category = business.get("category", "default")
        processed_competitor = process_reviews_batch(reviews, category)
        processed_target = process_reviews_batch(target_reviews, category)

        # Save to DB
        comp_saved = save_reviews(business_id, processed_competitor, source="competitor")
        target_saved = save_reviews(business_id, processed_target, source="own")

        total_saved = comp_saved + target_saved
        log_cron_end(log_id, "success", reviews_collected=total_saved,
                     competitors_scraped=len(comp_urls))
        logger.info(f"Cron job completed: {total_saved} new reviews saved from {len(comp_urls)} competitors")

    except Exception as e:
        log_cron_end(log_id, "error", error_msg=str(e))
        logger.error(f"Cron job failed: {e}", exc_info=True)


def start_scheduler():
    """Start the background scheduler with daily jobs."""
    if scheduler.running:
        logger.info("Scheduler already running.")
        return

    # Run at 08:00, 14:00, 22:00 daily
    scheduler.add_job(
        collect_reviews_job,
        CronTrigger(hour="8,14,22", minute=0),
        id="daily_scrape",
        name="Daily Review Collection",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: jobs at 08:00, 14:00, 22:00 daily")


def stop_scheduler():
    """Stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


def run_scrape_now():
    """Manually trigger a scrape job (for testing or on-demand)."""
    logger.info("Manual scrape triggered.")
    collect_reviews_job()
