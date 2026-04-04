from scraper import search_businesses_sync

def test_search():
    print("Searching for barbers in Izmir Buca to see if we get all businesses (~150 limit)...")
    res = search_businesses_sync("Barber", "Izmir", "Buca", "Turkey", 150)
    
    if "error" in res and res["error"]:
        print(f"Error: {res['error']}")
    else:
        businesses = res.get("businesses", [])
        print(f"\nFound {len(businesses)} total local businesses!")
        if businesses:
            print("First 5:")
            for b in businesses[:5]:
                print(f"- {b['name']}")
            print("...")
            print("Last 5:")
            for b in businesses[-5:]:
                print(f"- {b['name']}")

if __name__ == "__main__":
    test_search()
