import os
import json
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from config import config_lg
# -------------------- Playwright Search -------------------- #
def run_playwright_search(model_id):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(config_lg["url"], timeout=30000)
            page.wait_for_load_state("load")
            print("✅ LG homepage loaded.")

            page.click('button[aria-label="Search"]')
            page.fill('input[placeholder="Search LG"]', model_id)
            page.press('input[placeholder="Search LG"]', 'Enter')

            page.wait_for_selector('a.css-11xg6yi', timeout=10000)
            first_product = page.locator('a.css-11xg6yi').first
            product_url = first_product.get_attribute("href")

            if product_url:
                full_url = urljoin(config_lg["url"], product_url)
                print(f"✅ First product found by Playwright: {full_url}")
                return full_url
            else:
                print("❌ No product URL found by Playwright.")
                return None
        except PlaywrightTimeoutError as e:
            print("❌ Playwright timeout error:", e)
            return None
        except Exception as e:
            print("❌ Playwright search error:", e)
            return None
        finally:
            browser.close()

# -------------------- Selenium Setup -------------------- #
def get_selenium_driver(download_path=None):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("window-size=1920,1080")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
    if download_path:
        prefs = {
            "download.default_directory": os.path.abspath(download_path),
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
        }
        chrome_options.add_experimental_option("prefs", prefs)
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# -------------------- Fetch HTML -------------------- #
def fetch_page_data(driver, url, retries=3):
    for attempt in range(retries):
        try:
            driver.get(url)
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            return driver.page_source
        except Exception as e:
            print(f"[ERROR] Attempt {attempt + 1} failed for URL {url}: {e}")
            time.sleep(2)
    return None

# -------------------- Extract product URL from fallback search pages -------------------- #
def get_first_product_from_fallback(driver, search_url):
    print(f"🔎 Trying fallback search URL: {search_url}")
    html = fetch_page_data(driver, search_url)
    if not html:
        print("❌ Failed to load fallback search page.")
        return None
    soup = BeautifulSoup(html, "html.parser")
    # The product links in fallback pages have class 'css-11xg6yi' (same as Playwright)
    product_links = soup.select('a.css-11xg6yi')
    if not product_links:
        print("❌ No product links found in fallback search page.")
        return None
    first_link = product_links[0].get("href")
    if not first_link:
        print("❌ First product link has no href.")
        return None
    full_url = urljoin(config_lg["url"], first_link)
    print(f"✅ Found product URL from fallback: {full_url}")
    return full_url

# -------------------- Extract Product Data -------------------- #
def extract_product_data(html, config):
    soup = BeautifulSoup(html, "html.parser")

    def select(selector, attr=None, multi=False):
        elems = soup.select(selector)
        if not elems:
            return [] if multi else ""
        if multi:
            results = []
            for el in elems:
                if attr == "src":
                    val = el.get(attr)
                    if val:
                        val = val.strip()
                elif attr == "link":
                    val = el.get("href")
                    if val:
                        val = val.strip()
                else:
                    val = el.get_text(strip=True)
                if val:
                    results.append(val)
            return results
        el = elems[0]
        if attr == "src":
            return el.get(attr).strip() if el.get(attr) else ""
        elif attr == "link":
            return el.get("href").strip() if el.get("href") else ""
        else:
            return el.get_text(strip=True)

    model_id = select(config["items"][0]["selector"])
    title = select(config["items"][1]["selector"])
    breadcrumb_elems = soup.select(config["items"][2]["selector"])
    category = " > ".join([el.get_text(strip=True) for el in breadcrumb_elems]) if breadcrumb_elems else ""

    key_features = select(config["items"][3]["selector"], multi=True)
    detailed_features = select(config["items"][4]["selector"], multi=True)
    features = list(dict.fromkeys(key_features + detailed_features))

    raw_images = select(config["items"][5]["selector"], attr="src", multi=True)
    image_urls = []
    for url in raw_images:
        if not url or url.startswith("data:"):
            continue
        image_urls.append(urljoin(config_lg["url"], url))
    image_urls = list(set(image_urls))

    manual_urls = select(config["items"][6]["selector"], attr="link", multi=True)
    manual_urls = [urljoin(config_lg["url"], url) for url in manual_urls]

    return model_id, title, features, image_urls, category, manual_urls

# -------------------- Save to JSON -------------------- #
def save_data_to_json(product_data, filename="lg_data.json"):
    all_data = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                all_data = json.load(f)
            except json.JSONDecodeError:
                pass
    all_data.append(product_data)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2)
    print(f"✅ Product data saved to {filename}")

# -------------------- Main -------------------- #
if __name__ == "__main__":
    driver = get_selenium_driver()
    try:
        model_id_input = input("Enter LG model ID (e.g., OLED55C2PUA): ").strip()
        if not model_id_input:
            print("❌ Please enter a valid model ID.")
            exit(1)

        # First try Playwright search
        product_url = run_playwright_search(model_id_input)

        # If Playwright search fails, try fallback URLs
        if not product_url:
            fallback_urls = config_lg["fallback_urls"]
            product_url = None
            for key in ["default", "category_url", "key_url", "image_url"]:
                search_url = fallback_urls[key].format(model_id=model_id_input)
                product_url = get_first_product_from_fallback(driver, search_url)
                if product_url:
                    break

        # If still no product URL, try manual support page fallback
        if not product_url:
            manual_page_url = config_lg["fallback_urls"]["manual_url"].format(model_id=model_id_input)
            print(f"🔎 Trying manual support URL as last resort: {manual_page_url}")
            # Check if manual page exists by loading it
            html = fetch_page_data(driver, manual_page_url)
            if html:
                product_url = manual_page_url
                print(f"✅ Using manual support page URL: {product_url}")

        if not product_url:
            print("❌ Product not found by any search method.")
            exit(1)

        html = fetch_page_data(driver, product_url)
        if not html:
            print("❌ Failed to load product page.")
            exit(1)

        model_id, title, features, image_urls, category, manual_urls = extract_product_data(html, config_lg)

        product_data = {
            "manufacturer": "LG",
            "model_id": model_id,
            "title": title,
            "category": category,
            "features": features,
            "images": image_urls,
            "manuals": manual_urls,
            "product_url": product_url,
        }

        save_data_to_json(product_data)

    finally:
        driver.quit()
