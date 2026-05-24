from playwright.sync_api import sync_playwright
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv

BASE_URL = "https://www.danmurphys.com.au/"
PID_URL = "https://www.danmurphys.com.au/product/DM_{}"
MAX_WORKERS = 10

def category_ids(category_url, max_pages):
    product_ids = []

    with sync_playwright() as p:
        # Page setup
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        for page_num in range(1, max_pages+1):
            # Open page
            url = f"{category_url}?page={page_num}"
            print(f"Scraping page {page_num}: {url}")
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            # Extract all product links
            links = page.eval_on_selector_all(
                "a[href*='/product/DM_']",
                "elements => elements.map(el => el.getAttribute('href'))"
            )

            # Stop if there are no more products
            if not links:
                print("No more products found. Stopping.")
                break

            # Extract unique DM IDs
            for link in links:
                match = re.search(r"DM_(\d+)", link)
                if match:
                    product_ids.append(match.group(1))
    
        browser.close()
    return list(set(product_ids))

def write_ids(ids, filename):
    fieldnames = ["product ids", "url"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames = fieldnames)
        writer.writeheader()
        for pid in ids:
            writer.writerow({"product ids": pid, "url": PID_URL.format(pid)})

ids = category_ids("https://www.danmurphys.com.au/beer/all", round(756/25)+2)
write_ids(ids, "BeerIDs.csv")