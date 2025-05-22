import os
import sys
import json
import time
import re
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# -------------------- Config Paths -------------------- #

CONFIG_PATH = r'C:\Users\sarav\Desktop\spiders\config\config.json'
SPIDERS_PATH = r'C:\Users\sarav\Desktop\spiders\spiders\whirlpool.json'
BASE_FOLDER = "output"
os.makedirs(BASE_FOLDER, exist_ok=True)

if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'r') as f:
        config_list = json.load(f)
else:
    print("[ERROR] Config file not found.")
    sys.exit(1)

if os.path.exists(SPIDERS_PATH):
    with open(SPIDERS_PATH, 'r') as f:
        whirlpool_config = json.load(f)
else:
    print("[ERROR] Whirlpool spider input file not found.")
    sys.exit(1)

# -------------------- Playwright Search -------------------- #

def run_playwright_search(model_id, category, base_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(base_url, timeout=60000)
            print("Whirlpool homepage loaded.")

            # Try to close modals
            modal_selectors = [
                ".conversion-drawer-tab__open-close",
                ".lead-gen-modal__content .close",
                "//button[@aria-label='Close']",
                ".modal-close-button",
            ]
            for selector in modal_selectors:
                try:
                    btn = page.locator(f"xpath={selector}" if selector.startswith("//") else selector)
                    if btn and btn.is_visible():
                        btn.click()
                        print(f"Closed modal: {selector}")
                        time.sleep(1)
                except Exception:
                    pass

            search_input = page.locator('input.header-search-input[aria-label="Search"]').first
            search_input.wait_for(state="visible", timeout=15000)
            search_input.fill(f'{model_id} {category}'.strip())
            search_input.press("Enter")
            print(f"Search performed for model ID: {model_id}")
            page.wait_for_load_state("load", timeout=60000)

            product_items = page.locator("div.plp-item[data-item-major='true']")
            count = product_items.count()

            if count == 0:
                print("[ERROR] No product items found.")
                return None

            for i in range(count):
                sku = product_items.nth(i).get_attribute("data-product-sku")
                if sku and model_id.lower() in sku.lower():
                    link = product_items.nth(i).locator("a").first
                    href = link.get_attribute("href")
                    if href:
                        full_url = urljoin(base_url, href)
                        return full_url

            fallback_link = product_items.first.locator("a").first.get_attribute("href")
            return urljoin(base_url, fallback_link) if fallback_link else None

        finally:
            browser.close()

# -------------------- Selenium Setup -------------------- #

def get_selenium_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

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
            print(f"[ERROR] Attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    return None

# -------------------- Data Extraction -------------------- #

def extract_background_image_url(style_attr):
    match = re.search(r'url\(["\']?(.*?)["\']?\)', style_attr)
    return match.group(1) if match else None

def extract_product_data(html, config, base_url):
    soup = BeautifulSoup(html, "html.parser")

    def select_data(selector, match="first", attr=None):
        elements = soup.select(selector)
        if not elements:
            return [] if match == "all" else ""

        if match == "all":
            results = []
            for el in elements:
                if attr and el.has_attr(attr):
                    url = urljoin(base_url, el[attr])
                    results.append(url)
                else:
                    text = el.get_text(strip=True)
                    if text:
                        results.append(text)
            return list(set(results))
        else:
            el = elements[0]
            return urljoin(base_url, el[attr]) if attr and el.has_attr(attr) else el.get_text(strip=True)

    title = select_data(config["items"][0]["selector"])
    key_features = []
    kf_elem = soup.select_one(config["items"][1]["selector"])
    if kf_elem:
        lis = kf_elem.find_all("li")
        if lis:
            key_features = [li.get_text(strip=True) for li in lis if li.get_text(strip=True) != "•"]
        else:
            raw = kf_elem.get_text(separator="|", strip=True)
            key_features = [i for i in raw.split("|") if i.strip()]

    image_urls = select_data(
        config["items"][2]["selector"],
        match=config["items"][2]["match"],
        attr=config["items"][2]["type"]
    )
    if not isinstance(image_urls, list):
        image_urls = [image_urls] if image_urls else []

    for div in soup.select("div.s7thumb"):
        url = extract_background_image_url(div.get("style", ""))
        if url:
            image_urls.append(urljoin(base_url, url))

    manual_url = select_data(
        config["items"][3]["selector"],
        match=config["items"][3]["match"],
        attr=config["items"][3]["type"]
    )

    if not manual_url:
        pdfs = [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True) if a["href"].endswith(".pdf")]
        manuals = [p for p in pdfs if "manual" in p.lower()]
        manual_url = manuals[0] if manuals else (pdfs[0] if pdfs else "")

    return title, key_features, image_urls, manual_url

# -------------------- Save Output -------------------- #

def save_data_to_json(data, filename):
    all_data = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                all_data = json.load(f)
            except:
                all_data = []
    all_data.append(data)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2)
    print(f"[SUCCESS] Saved to {filename}")

# -------------------- MAIN -------------------- #

if __name__ == "__main__":
    driver = get_selenium_driver()
    try:
        base_url = whirlpool_config["url"]
        for entry in config_list:
            model_id = entry["model_id"].strip()
            category = entry.get("category", "").strip()
            manufacturer = entry["manufacturer"].strip().lower()

            if manufacturer != "whirlpool":
                print(f"[SKIPPED] Not Whirlpool: {manufacturer}")
                continue

            print(f"\n[INFO] Processing: {manufacturer} - {model_id}")
            product_url = run_playwright_search(model_id, category, base_url)

            if not product_url:
                print("[ERROR] Product URL not found.")
                continue

            html = fetch_page_data(driver, product_url)
            if not html:
                print("[ERROR] Failed to fetch product page.")
                continue

            title, features, images, manual = extract_product_data(html, whirlpool_config, product_url)
            product_data = {
                "title": title,
                "key_features": features,
                "image_urls": images,
                "manual_url": manual,
                "product_url": product_url,
            }

            output_file = os.path.join(BASE_FOLDER, f"{manufacturer}.json")
            save_data_to_json(product_data, output_file)

    finally:
        driver.quit()
