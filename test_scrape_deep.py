import asyncio
import json
from scraper import search_businesses_sync, deep_scrape_competitors_sync

def test():
    print("Searching...")
    search_res = search_businesses_sync("Berber", "İstanbul", "Kadıköy", "Türkiye", 5)
    
    if "error" in search_res:
        print("Search Error:", search_res["error"])
        return
        
    businesses = search_res.get("businesses", [])
    print(f"Found {len(businesses)} businesses.")
    
    if not businesses:
        return
        
    urls = [b["url"] for b in businesses]
    target_url = urls[0] if urls else None
    
    print(f"Deep scraping competitors, excluding target: {target_url}")
    scrape_res = deep_scrape_competitors_sync(urls, target_url, "Türkiye", min_target_reviews=20)
    
    print("\nScrape Results:")
    print(f"Total reviews: {scrape_res.get('total_reviews')}")
    print(f"Error (if any): {scrape_res.get('error')}")

if __name__ == "__main__":
    test()
