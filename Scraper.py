from bs4 import BeautifulSoup as bs
import re
import time
import random
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import asyncio
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright


# Config
BASE_URL = "https://www.danmurphys.com.au/product/{}"
START_ID = 1
END_ID = 1000000          # Candidate product IDs
PRODUCT_IDS = ["446855", "907623", "809797", "98903"]
CSV_FILE = "products.csv"
MAX_WORKERS = 20          # Threads for parallel requests

# parser, get info
def parse_product(html):
    soup = bs(html, "html.parser")

    # get product title
    title_tag = soup.select_one("h1.product-title .product-title__name")
    product_title = title_tag.get_text(strip=True) if title_tag else None
    if not product_title:
        return []

    # find packs
    packs = []
    for button in soup.select("button.pack"):
        # Extract pack type
        quantity_span = button.select_one(".pack__type span")
        quantity_text = quantity_span.get_text(strip = True) if quantity_span else ""
        match = re.search(r"\((\d+)\)", quantity_text)
        quantity = float(match.group(1)) if match else 1

        # Extract price
        price_div = button.select_one(".pack__price")
        price_text = price_div.get_text(strip=True) if price_div else ""
        match = re.search(r"\$([\d.]+)", price_text)
        price = float(match.group(1)) if match else None

        if quantity and price:
            packs.append({
                "quantity": quantity,
                "price": price
            })

    # get attributes
    attributes = {}
    for li in soup.select("ul.product-attribute__items li.product-attribute__item"):
        # Extract pack type
        key_span = li.select_one(".product-attribute__item-key")
        value_span = li.select_one(".product-attribute__item-value")

        if key_span and value_span:
            key = key_span.get_text(strip=True)
            value = value_span.get_text(strip=True)
            attributes[key] = value

    # give relevant info on standard drinks
    sd_info = []
    for pack in packs:
        brand = attributes.get("Brand Name", None)
        product = product_title
        price = pack['price']
        quantity = pack['quantity']
        sd_per_quantity = float(attributes.get("Standard Drinks", 0))
        sd = sd_per_quantity * quantity
        alc = float(re.search(r"([\d.]+)", attributes.get("Alcohol Volume", 0)).group(1))/100
        vol = float(re.search(r"([\d.]+)", attributes.get("Size", 0)).group(1))
        if "ML" in attributes.get("Size", 0): # Convert to Litres
            vol = vol/1000
        sd_estimate = vol*alc*789.45/10*quantity
        price_per_sd = price / sd if sd else None

        sd_info.append({
            "brand": brand,
            "product": product,
            "quantity": quantity,
            "price": price,
            "standard drinks": round(sd, 2),
            "standard drinks estimate": round(sd_estimate, 2),
            "price per sd": round(price_per_sd, 2),
        })
    print("TITLE LIST:", product_title)
    return sd_info

# Write results incrementally
def write_csv(rows, name):
    fieldnames = ["pid", "brand", "product", "quantity", "price", "standard drinks", "standard drinks estimate", "price per sd"]
    with open(name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

# Main scraper
def scrape_products(product_ids):
    all_rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
            })
            """)
        context.route("**/*", lambda route, request:
            route.abort() if request.resource_type in ["image", "media", "font", "stylesheet", "manifest", "eventsource"]
            else route.continue_()
        )
        page = context.new_page()
        for pid in product_ids:
            url = BASE_URL.format(f"DM_{pid}")
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_selector("h1.product-title .product-title__name", timeout=5000, state="attached")  # wait for JS
                html = page.content()
                product_data = parse_product(html)
                for row in product_data:
                    row["pid"] = pid
                all_rows.extend(product_data)
            except Exception as e:
                print("URL:", page.url)
                print("Title:", page.title())
                print(f"Error fetching {url}: {e}")
            #finally:
                #page.close()

            #time.sleep(random.uniform(0.5, 1.5))
        browser.close()
    return all_rows

async def scrape_one(pid, context, semaphore, timeout):
    async with semaphore:
        page = await context.new_page()
        try:
            url = BASE_URL.format(f"DM_{pid}")
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector("h1.product-title .product-title__name", timeout= timeout)

            html = await page.content()
            data = parse_product(html)
            for row in data:
                row["pid"] = pid
            return data
        except Exception as e:
            print("URL:", page.url)
            print("Title:", page.title())
            print(f"Error fetching {url}: {e}")
            return []
        finally:
            await page.close()

# Give workers set pages
async def worker(name, page, queue, results):
    while True:
        pid = await queue.get()
        if pid is None:  # shutdown signal
            queue.task_done()
            break

        try:
            await page.goto("about:blank")


            url = BASE_URL.format(f"DM_{pid}")
            await page.goto(url, wait_until="domcontentloaded")

            title_locator = page.locator("h1.product-title .product-title__name")
            await title_locator.wait_for(state="attached", timeout=8000)
            title = await title_locator.inner_text()

            results.append({
                "pid": pid,
                "title": title
            })

        except Exception as e:
            print(f"[Worker {name}] Failed {pid}: {e}")

        finally:
            queue.task_done()

# Scraper but static pages, i.e. pages don't close
async def scrape_products_async_static(product_ids, workers):
    CONCURRENCY = workers
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
            })
            """)
        context.route("**/*", lambda route, request:
            route.abort() if request.resource_type in ["image", "media", "font", "stylesheet", "manifest", "eventsource"]
            else route.continue_()
        )

        # Create fixed worker pages
        pages = [await context.new_page() for _ in range(CONCURRENCY)]
        queue = asyncio.Queue()

        # Fill queue
        for pid in product_ids:
            await queue.put(pid)

        # Start workers
        tasks = [asyncio.create_task(worker(i, pages[i], queue, results)) for i in range(CONCURRENCY)]

        # Wait until all tasks processed
        await queue.join()

        # Stop workers
        for _ in range(CONCURRENCY):
            await queue.put(None)

        await asyncio.gather(*tasks)
        await browser.close()
    return results

# Scrape product info 
async def scrape_products_async(product_ids, workers):
    CONCURRENCY = workers
    all_rows = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]
        context = await browser.new_context(user_agent=random.choice(USER_AGENTS), viewport={"width": 1280, "height": 800}, locale="en-AU", timezone_id="Australia/Sydney",)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            """)
        await context.route("**/*", lambda route, request:
            route.abort() if request.resource_type in ["image", "media", "font", "stylesheet", "manifest", "eventsource"]
            else route.continue_()
        )
        semaphore = asyncio.Semaphore(CONCURRENCY)

        tasks = [scrape_one(pid, context, semaphore, 2500*workers) for pid in product_ids]
        results = await asyncio.gather(*tasks)

        for result in results:
            all_rows.extend(result)

        await browser.close()

    return all_rows

# def scrape_products_thread(product_ids):
#     with ThreadPoolExecutor(max_workers=4) as executor:
#         results = executor.map(lambda pid: scrape_products(pid), product_ids)

def scrape_id(pid):
    return scrape_products([pid])  # pass a list with 1 ID

def page_exists(product_id):
    url = f"https://www.danmurphys.com.au/product/DM_{product_id}"
    resp = requests.head(url, allow_redirects=True)
    return resp.status_code == 200

def check_and_return(pid):
    if page_exists(pid):
        return pid
    return None

def thread_existing_pids(pid):
    with ThreadPoolExecutor(max_workers=10) as executor:
        existing_ids = [pid for pid in executor.map(check_and_return, range(860340, 860400)) if pid]
    return existing_ids

def thread_scrape(scrape_id, PRODUCT_IDS):
    all_rows = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for result in executor.map(scrape_id, PRODUCT_IDS):
            if result:
                all_rows.extend(result)
                write_csv(all_rows)
    return all_rows

def read_pids(file):
    PRODUCT_IDS = []
    with open(file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            PRODUCT_IDS.append(row["product ids"])
    return PRODUCT_IDS

#PRODUCT_IDS = ['6026365', '601563', '746009', '331438', '6026363', '334184', '387419', '904904', '226194', '911699', '293740', '746013', '947193', '910502', '213728', '915237', '910429', '907490', '561680']
PRODUCT_IDS = read_pids("BeerIDs.csv")
rows = asyncio.run(scrape_products_async(PRODUCT_IDS, 5))
write_csv(rows, "BeerProducts.csv")
print("Scraping complete")

exit()

# For 100 IDs,
# 2 workers is 410 or 4.1 seconds per ID, two errors
# 3 workers is 350 or 3.5 seconds per ID, one error
# 4 workers is 320 or 3.2 seconds per ID
# 5 workers is <240 or <2.4 seconds per ID, one error with 12.5s wait time
# 6 workers produces too many errors

PRODUCT_IDS = read_pids("Cider.csv")
rows = scrape_products(PRODUCT_IDS)
write_csv(rows)
print("Scraping complete")