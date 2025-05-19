import os
import sys
import json
import time
import re
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from config import config_whirlpool


# -------------------- Playwright Search -------------------- #

def run_playwright_search(model_id):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto("https://www.whirlpool.com/", timeout=60000)
            print("✅ Whirlpool homepage loaded.")

            # Close modal/pop-ups if present
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
                        print(f"✅ Closed modal: {selector}")
                        time.sleep(1)
                except Exception:
                    # Continue if modal not found or cannot be closed
                    pass

            # Perform search
            search_input = page.locator('input.header-search-input[aria-label="Search"]').first
            search_input.wait_for(state="visible", timeout=15000)
            search_input.fill(model_id)
            search_input.press("Enter")
            print(f"✅ Search performed for model ID: {model_id}")

            page.wait_for_load_state("load", timeout=60000)
            product_link = page.locator('a.plp-item-detail-link').first

            if product_link.count() == 0:
                print("[ERROR] No product links found.")
                return None

            product_url = product_link.get_attribute("href")

            if product_url:
                full_url = urljoin("https://www.whirlpool.com", product_url)
                print(f"✅ Found product URL: {full_url}")
                return full_url
            else:
                print("[ERROR] Product link missing href.")
                return None
        except PlaywrightTimeoutError:
            print("[ERROR] Timeout while loading Whirlpool homepage or search results.")
            return None
        finally:
            browser.close()


# -------------------- Selenium Setup -------------------- #
def get_selenium_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


# -------------------- Fetch Page Content -------------------- #
def fetch_page_data(driver, url, retries=3):
    for attempt in range(retries):
        try:
            driver.get(url)
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, config_whirlpool["items"][5]["selector"]))
            )
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            print(f"✅ Page loaded: {url}")
            return driver.page_source
        except Exception as e:
            print(f"[ERROR] Attempt {attempt + 1} failed: {e}")
            time.sleep(3)
    return None


# -------------------- Extract Background Image from Style -------------------- #
def extract_background_image_url(style_attr):
    if not style_attr:
        return None
    match = re.search(r'url\(["\']?(.*?)["\']?\)', style_attr)
    return match.group(1) if match else None


# -------------------- Parse HTML Content -------------------- #
def extract_product_data(html, config, base_url):
    soup = BeautifulSoup(html, "html.parser")

    def select_data(selector, attr=None, multiple=False):
        elements = soup.select(selector)
        if not elements:
            return [] if multiple else ""
        if multiple:
            result = []
            for el in elements:
                if attr and el.has_attr(attr):
                    url = urljoin(base_url, el[attr])
                    result.append(url)
                else:
                    text = el.get_text(strip=True)
                    if text:
                        result.append(text)
            return list(set(result))  # remove duplicates
        el = elements[0]
        if attr and el.has_attr(attr):
            return urljoin(base_url, el[attr])
        return el.get_text(strip=True)

    model_id = select_data(config["items"][0]["selector"])
    title = select_data(config["items"][1]["selector"])
    category_elements = soup.select(config["items"][5]["selector"])
    category = " > ".join(el.get_text(strip=True) for el in category_elements) if category_elements else ""

    # Manual link extraction
    pdf_links = [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]
    manual_url = ""
    if pdf_links:
        manual_candidates = [link for link in pdf_links if "manual" in link.lower()]
        manual_url = manual_candidates[0] if manual_candidates else pdf_links[0]

    # Images
    image_urls = select_data(config["items"][3]["selector"], attr="src", multiple=True) or []
    # Also check background images in div.s7thumb
    for div in soup.select("div.s7thumb"):
        style_url = extract_background_image_url(div.get("style", ""))
        if style_url:
            full_url = urljoin(base_url, style_url)
            if full_url not in image_urls:
                image_urls.append(full_url)

    # Key features
    key_features_div = soup.select_one(config["items"][2]["selector"])
    key_features = []
    if key_features_div:
        lis = key_features_div.find_all("li")
        if lis:
            key_features = [li.get_text(strip=True) for li in lis if li.get_text(strip=True) != "•"]
        else:
            raw = key_features_div.get_text(separator="|", strip=True)
            key_features = [f.strip() for f in raw.split("|") if f.strip() and f != "•"]

    return model_id, title, key_features, image_urls, manual_url, category


# -------------------- Save to JSON -------------------- #
def save_data_to_json(data, filename="whirlpool.json"):
    all_data = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                all_data = json.load(f)
            except json.JSONDecodeError:
                all_data = []
    all_data.append(data)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2)
    print(f"[SUCCESS] Data saved to {filename}")


# -------------------- Main -------------------- #
if __name__ == "__main__":
    driver = get_selenium_driver()
    try:
        model_id_input = input("Enter Whirlpool model ID (e.g., WFE505W0JZ): ").strip()
        product_url = run_playwright_search(model_id_input)

        # If Playwright fails, fall back to predefined URLs
        if not product_url:
            print("[INFO] Falling back to predefined URLs...")
            fallback_attempted = False
            for url_key in config_whirlpool.get("fallback_urls", {}):
                fallback_url = config_whirlpool["fallback_urls"][url_key].format(model_id=model_id_input)
                html = fetch_page_data(driver, fallback_url)
                if html:
                    print(f"✅ Fallback URL worked: {fallback_url}")
                    product_url = fallback_url
                    fallback_attempted = True
                    break
            if not fallback_attempted:
                print("[ERROR] Model not found even using fallback URLs.")
                sys.exit(1)

        html = fetch_page_data(driver, product_url)
        if not html:
            print("[ERROR] Failed to load product page.")
            sys.exit(1)

        model_id, title, features, images, manual_url, category = extract_product_data(
            html, config_whirlpool, product_url
        )

        product_data = {
            "manufacturer": "whirlpool",
            "model_id": model_id,
            "title": title,
            "category": category,
            "key_features": features,
            "image_urls": images,
            "manual_url": manual_url,
            "product_url": product_url
        }

        save_data_to_json(product_data)

    finally:
        driver.quit()
