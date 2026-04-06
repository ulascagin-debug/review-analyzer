"""
Google Maps Review Scraper using Playwright.
Scrapes competitor reviews without requiring any API key.
No Google login needed — fully anonymous.
OPTIMIZED: Parallel scraping with multiple tabs.
LOCALE-AWARE: Uses the correct locale for the target country.
DEDUP: Prevents duplicate reviews.
TWO-STEP: Supports searching businesses first, then deep scraping selected competitors.
"""

import asyncio
import re
from playwright.async_api import async_playwright

# Country → locale + consent text mapping
COUNTRY_LOCALE_MAP = {
    "türkiye": {"locale": "tr-TR", "consent": ["Tümünü kabul et"]},
    "turkey": {"locale": "tr-TR", "consent": ["Tümünü kabul et"]},
    "deutschland": {"locale": "de-DE", "consent": ["Alle akzeptieren"]},
    "germany": {"locale": "de-DE", "consent": ["Alle akzeptieren"]},
    "österreich": {"locale": "de-AT", "consent": ["Alle akzeptieren"]},
    "austria": {"locale": "de-AT", "consent": ["Alle akzeptieren"]},
    "schweiz": {"locale": "de-CH", "consent": ["Alle akzeptieren"]},
    "switzerland": {"locale": "de-CH", "consent": ["Alle akzeptieren"]},
    "france": {"locale": "fr-FR", "consent": ["Tout accepter"]},
    "belgique": {"locale": "fr-BE", "consent": ["Tout accepter"]},
    "belgium": {"locale": "fr-BE", "consent": ["Tout accepter"]},
    "españa": {"locale": "es-ES", "consent": ["Aceptar todo"]},
    "spain": {"locale": "es-ES", "consent": ["Aceptar todo"]},
    "méxico": {"locale": "es-MX", "consent": ["Aceptar todo"]},
    "mexico": {"locale": "es-MX", "consent": ["Aceptar todo"]},
    "argentina": {"locale": "es-AR", "consent": ["Aceptar todo"]},
    "colombia": {"locale": "es-CO", "consent": ["Aceptar todo"]},
    "portugal": {"locale": "pt-PT", "consent": ["Aceitar tudo"]},
    "brasil": {"locale": "pt-BR", "consent": ["Aceitar tudo"]},
    "brazil": {"locale": "pt-BR", "consent": ["Aceitar tudo"]},
    "italia": {"locale": "it-IT", "consent": ["Accetta tutto"]},
    "italy": {"locale": "it-IT", "consent": ["Accetta tutto"]},
    "nederland": {"locale": "nl-NL", "consent": ["Alles accepteren"]},
    "netherlands": {"locale": "nl-NL", "consent": ["Alles accepteren"]},
    "polska": {"locale": "pl-PL", "consent": ["Zaakceptuj wszystko"]},
    "poland": {"locale": "pl-PL", "consent": ["Zaakceptuj wszystko"]},
    "россия": {"locale": "ru-RU", "consent": ["Принять все"]},
    "russia": {"locale": "ru-RU", "consent": ["Принять все"]},
    "ελλάδα": {"locale": "el-GR", "consent": ["Αποδοχή όλων"]},
    "greece": {"locale": "el-GR", "consent": ["Αποδοχή όλων"]},
    "السعودية": {"locale": "ar-SA", "consent": ["قبول الكل"]},
    "saudi arabia": {"locale": "ar-SA", "consent": ["قبول الكل"]},
    "مصر": {"locale": "ar-EG", "consent": ["قبول الكل"]},
    "egypt": {"locale": "ar-EG", "consent": ["قبول الكل"]},
    "日本": {"locale": "ja-JP", "consent": ["すべて同意"]},
    "japan": {"locale": "ja-JP", "consent": ["すべて同意"]},
    "한국": {"locale": "ko-KR", "consent": ["모두 동의"]},
    "south korea": {"locale": "ko-KR", "consent": ["모두 동의"]},
    "中国": {"locale": "zh-CN", "consent": ["全部接受"]},
    "china": {"locale": "zh-CN", "consent": ["全部接受"]},
    "united states": {"locale": "en-US", "consent": ["Accept all"]},
    "usa": {"locale": "en-US", "consent": ["Accept all"]},
    "united kingdom": {"locale": "en-GB", "consent": ["Accept all"]},
    "uk": {"locale": "en-GB", "consent": ["Accept all"]},
    "canada": {"locale": "en-CA", "consent": ["Accept all"]},
    "australia": {"locale": "en-AU", "consent": ["Accept all"]},
}

REVIEWS_TAB_TEXTS = [
    "Reviews", "Yorumlar", "Bewertungen", "Avis", "Reseñas", "Avaliações",
    "Recensioni", "Beoordelingen", "Opinie", "Отзывы", "Κριτικές",
    "التعليقات", "クチコミ", "리뷰", "评论",
]

def get_locale_config(country):
    if not country: return "en-US", ["Accept all", "Tümünü kabul et"]
    config = COUNTRY_LOCALE_MAP.get(country.strip().lower(), None)
    return (config["locale"], config["consent"]) if config else ("en-US", ["Accept all"])


async def handle_consent(page, consent_texts):
    try:
        consent_selectors = [f'button:has-text("{t}")' for t in consent_texts] + [
            'button:has-text("Accept all")', 'button:has-text("Tümünü kabul et")',
            'form[action*="consent"] button', 'button[aria-label*="Accept"]'
        ]
        for sel in consent_selectors:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click()
                await page.wait_for_timeout(1500)
                break
    except Exception:
        pass


async def _search_businesses_logic(category, city, district, country, max_businesses=30):
    query = f"{category} in {city}"
    if district: query = f"{category} in {district}, {city}"
    maps_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"

    locale, consent_texts = get_locale_config(country)
    businesses = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, 
            locale=locale,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())
        page = await context.new_page()

        try:
            await page.goto(maps_url, timeout=30000)
            await page.wait_for_timeout(2000)
            await handle_consent(page, consent_texts)
            await page.wait_for_timeout(2000)

            feed_selector = 'div[role="feed"]'
            try:
                await page.wait_for_selector(feed_selector, timeout=10000)
            except:
                await page.wait_for_timeout(2000)

            # Check if Google Maps redirected directly to the exact place
            if "/maps/place/" in page.url:
                name_el = page.locator('h1').first
                name = await name_el.inner_text() if await name_el.count() > 0 else category
                return {"businesses": [{"name": name.strip(), "url": page.url}]}

            feed = page.locator(feed_selector)
            if await feed.count() > 0:
                for _ in range(30):
                    await feed.evaluate('el => el.scrollTop = el.scrollHeight')
                    await page.wait_for_timeout(800)

            # Find all links in the feed
            entries = page.locator('a[href*="/maps/place/"]')
            entry_count = await entries.count()
            
            seen_hrefs = set()
            for i in range(entry_count):
                try:
                    href = await entries.nth(i).get_attribute("href")
                    if href and "/maps/place/" in href and href not in seen_hrefs:
                        seen_hrefs.add(href)
                        # Try to get the aria-label which usually contains the business name
                        name = await entries.nth(i).get_attribute("aria-label") or "Unknown Business"
                        businesses.append({
                            "name": name,
                            "url": href
                        })
                        if len(businesses) >= max_businesses: break
                except:
                    continue

        except Exception as e:
            return {"error": str(e), "businesses": []}
        finally:
            await browser.close()

    return {"businesses": businesses}


def search_businesses_sync(category, city, district="", country="", max_businesses=30):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_search_businesses_logic(category, city, district, country, max_businesses))
        loop.close()
        return result
    except Exception as e:
        return {"error": str(e), "businesses": []}


async def scrape_single_business(context, href, max_scrolls=8):
    """Deep scrape a single business to get many reviews."""
    page = await context.new_page()
    business_name = ""
    reviews = []

    try:
        await page.goto(href, timeout=30000)
        await page.wait_for_timeout(500)

        name_el = page.locator('h1').first
        name_el = page.locator('h1').first
        if await name_el.count() > 0:
            business_name = (await name_el.inner_text()).strip()
            print(f"Opened business: {business_name}")

        clicked = False
        for tab_text in REVIEWS_TAB_TEXTS:
            reviews_tab = page.locator('button[role="tab"]').filter(has_text=tab_text)
            if await reviews_tab.count() > 0:
                await reviews_tab.first.click()
                await page.wait_for_timeout(1000)
                clicked = True
                break

        if not clicked:
            all_tabs = page.locator('button[role="tab"]')
            if await all_tabs.count() >= 2:
                print("Clicking second tab as fallback")
                await all_tabs.nth(1).click()
                await page.wait_for_timeout(2000)

        # Deep scroll to load many reviews
        scrollable = page.locator('div.m6QErb.DxyBCb.kA9KIf.dS8AEf')
        scroll_count = await scrollable.count()
        print(f"Found {scroll_count} scrollable elements")
        if scroll_count > 0:
            last_height = 0
            for _ in range(max_scrolls):
                new_height = await scrollable.evaluate('el => el.scrollHeight')
                if new_height == last_height and _ > 1:
                    break
                await scrollable.evaluate('el => el.scrollTop = el.scrollHeight')
                await page.wait_for_timeout(400)
                last_height = new_height

        # Expand truncated review texts using JS instantly
        await page.evaluate("""() => {
            document.querySelectorAll('button.w8nwRe.kyuRq').forEach(b => b.click());
        }""")

        # New classes might be .jftiEf
        review_cards = page.locator('div[data-review-id], .jftiEf')
        card_count = await review_cards.count()
        print(f"Found {card_count} rev cards")

        for j in range(card_count):
            try:
                card = review_cards.nth(j)
                rating = 0
                star_el = card.locator('span[role="img"], .kvDRne').first
                if await star_el.count() > 0:
                    aria = await star_el.get_attribute("aria-label")
                    if aria:
                        match = re.search(r'(\d)', aria)
                        if match: rating = int(match.group(1))

                text = ""
                text_el = card.locator('span.wiI7pd, .wiI7cb').first
                if await text_el.count() > 0:
                    text = (await text_el.inner_text()).strip()

                if text and len(text) > 3:
                    reviews.append({"rating": rating, "text": text, "business": business_name})
            except Exception as e: print(f"Error parsing card: {e}")
            
        print(f"Scraped {len(reviews)} reviews for {business_name}")

    except Exception as e:
        print(f"Error in scrape_single_business: {e}")
    finally:
        await page.close()

    return reviews


async def _scrape_reviews_logic(business_urls, target_business_url=None, country="", min_target_reviews=100, max_target_reviews=400, parallel_tabs=3, min_businesses=5):
    """Scrapes a specific list of competitor URLs until the review target is met."""
    locale, consent_texts = get_locale_config(country)
    
    results = {"reviews": [], "target_reviews": [], "businesses_found": len(business_urls), "total_reviews": 0, "avg_rating": 0}
    all_reviews = []
    seen_texts = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, 
            locale=locale,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())

        try:
            # First, handle consent on a blank Google Maps page
            page = await context.new_page()
            await page.goto("https://www.google.com/maps", timeout=30000)
            await handle_consent(page, consent_texts)
            await page.close()

            if target_business_url:
                print("Scraping TARGET business...")
                tr = await scrape_single_business(context, target_business_url, max_scrolls=15)
                if isinstance(tr, list):
                    results["target_reviews"] = tr

            scraped_urls = 0
            for batch_start in range(0, len(business_urls), parallel_tabs):
                if len(all_reviews) >= min_target_reviews and scraped_urls >= min_businesses:
                    break # We have enough reviews AND enough businesses checked

                batch = business_urls[batch_start:batch_start + parallel_tabs]
                scraped_urls += len(batch)

                # Determine how deep to scroll
                if len(all_reviews) >= min_target_reviews:
                    scrolls = 2 # Shallow scrape since we hit review target but need more businesses
                else:
                    scrolls = 8 if len(all_reviews) < 100 else 4
                
                tasks = [scrape_single_business(context, href, scrolls) for href in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for result_batch in batch_results:
                    if isinstance(result_batch, list):
                        for r in result_batch:
                            dedup_key = r["text"].strip().lower()
                            if dedup_key not in seen_texts:
                                seen_texts.add(dedup_key)
                                all_reviews.append(r)
                                
            if len(all_reviews) > max_target_reviews:
                import random
                random.shuffle(all_reviews)
                all_reviews = all_reviews[:max_target_reviews]

            if all_reviews:
                total_rating_sum = sum(r["rating"] for r in all_reviews)
                results["reviews"] = all_reviews
                results["total_reviews"] = len(all_reviews)
                results["avg_rating"] = round(total_rating_sum / len(all_reviews), 1)
                results["businesses_analyzed"] = scraped_urls
            else:
                results["error"] = "No reviews found across the selected competitors."
                
        except Exception as e:
            results["error"] = str(e)
        finally:
            await browser.close()

    return results


def deep_scrape_competitors_sync(business_urls, target_business_url=None, country="", min_target_reviews=200):
    """Synchronous wrapper for deep scraping. Removes target business if provided."""
    try:
        # Filter out the user's business URL
        competitor_urls = []
        for url in business_urls:
            # Simple soft match or exact match to exclude the target business
            if target_business_url and target_business_url in url:
                continue
            if url and target_business_url and url in target_business_url:
                continue
            competitor_urls.append(url)
            
        if not competitor_urls:
            return {"error": "No competitors left after filtering.", "reviews": [], "total_reviews": 0}

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_scrape_reviews_logic(competitor_urls, target_business_url, country, min_target_reviews))
        loop.close()
        return result
    except Exception as e:
        return {"error": str(e), "reviews": [], "total_reviews": 0}
