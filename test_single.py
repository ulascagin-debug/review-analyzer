from scraper import scrape_single_business
import asyncio
from playwright.async_api import async_playwright
import time

async def quick_test():
    url = "https://www.google.com/maps/place/Levent+Bi%C3%A7ici+Hair+Studio/data=!4m7!3m6!1s0x14bbdf619ce1c6e1:0x41ba0db7ebc3347f!8m2!3d38.3756241!4d27.1714521!16s%2Fg%2F11rvclhsnz!19sChIJ4cbhnGG_uxQRfzTD67cNukE?authuser=0&hl=tr&rclk=1"
    print("Testing single business scrape...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, 
            locale="tr-TR",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        from scraper import handle_consent
        
        # Handle consent first
        consent_page = await context.new_page()
        await consent_page.goto("https://www.google.com/maps", timeout=30000)
        await handle_consent(consent_page, ["Kabul ediyorum", "I agree"])
        await consent_page.close()
        
        reviews = await scrape_single_business(context, url, max_scrolls=2)
        print(f"Got {len(reviews)} reviews!")
        if reviews:
            print(f"Sample: {reviews[0]}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(quick_test())
