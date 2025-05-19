import os
import json
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from config import config_samsung

# -------------------- Playwright Search -------------------- #

def run_playwright_search(model_id, headless=True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto("https://www.samsung.com/us/")
        page.wait_for_load_state("load")

        try:
            consent_button = page.locator("button:has-text('Accept')").first
            if consent_button and consent_button.is_visible():
                consent_button.click(timeout=3000)
        except Exception:
            pass

        try:
            search_button = page.locator("div.nv00-gnb-v3__utility.search button[aria-label='Search']")
            search_button.click()
            page.wait_for_selector("input#gnb-search-keyword")
            search_input = page.locator("input#gnb-search-keyword")
            search_input.fill(model_id)
            search_input.press("Enter")
            page.wait_for_selector(".ProductCard__prodLink___3CTY0", timeout=15000)
            product_url = page.locator(".ProductCard__prodLink___3CTY0").first.get_attribute("href")
            return urljoin("https://www.samsung.com/us", product_url) if product_url else None
        except Exception as e:
            print(f"[ERROR] Playwright search failed: {e}")
            return None
        finally:
            browser.close()

# -------------------- Selenium Setup -------------------- #
def get_selenium_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# -------------------- Scraping Functions -------------------- #
def fetch_page_data(driver, url, retries=3):
    for attempt in range(retries):
        try:
            driver.get(url)
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            return driver.page_source
        except TimeoutException:
            print(f"[WARN] Timeout loading page, retrying ({attempt+1}/{retries})...")
        except Exception as e:
            print(f"[ERROR] Error during fetch: {e}")
    return None

def extract_product_data(html, config):
    soup = BeautifulSoup(html, "html.parser")

    def select_data(selector, attr=None, multiple=False):
        elements = soup.select(selector)
        if not elements:
            return [] if multiple else ""
        if multiple:
            values = []
            for el in elements:
                val = el.get(attr) if attr else el.get_text(strip=True)
                if val:
                    values.append(val)
            return list(dict.fromkeys(values))  
        return elements[0].get(attr) if attr else elements[0].get_text(strip=True)

    # Extract items
    def get_item(name):
        conf = next((item for item in config["items"] if item["name"] == name), None)
        if not conf:
            return "" if conf["match"] == "first" else []
        return select_data(
            selector=conf["selector"],
            attr=conf["type"] if conf["type"] in ("src", "href") else None,
            multiple=conf["match"] == "all"
        )

    model_id = get_item("model_id")
    title = get_item("title")
    icon_features = get_item("icon_features")
    detailed_features = get_item("detailed_features")
    key_features = get_item("key_features")
    raw_image_urls = get_item("images")
    breadcrumb_items = get_item("breadcrumb")
    pdf_urls = get_item("pdf_url")

    # Format
    image_urls = [urljoin("https://www.samsung.com", url) if url.startswith("//") else url for url in raw_image_urls]
    category = " > ".join(breadcrumb_items)
    manual_url = next((url for url in pdf_urls if "manual" in url.lower() or "user" in url.lower()), "")
    all_features = icon_features + detailed_features + key_features

    return model_id, title, all_features, image_urls, manual_url, category

def save_data_to_json(data, filename="samsung_data.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[DONE] Data saved to {filename}")

# -------------------- Main Execution -------------------- #
if __name__ == "__main__":
    headless_mode = True
    driver = get_selenium_driver(headless=headless_mode)

    model_input = input("Enter Samsung model IDs (comma-separated): ").strip()
    model_ids = [m.strip() for m in model_input.split(",") if m.strip()]

    if not model_ids:
        print("❌ No model IDs entered. Exiting.")
        exit(1)

    all_data = []

    try:
        for idx, model in enumerate(model_ids, 1):
            print(f"\n🔍 ({idx}/{len(model_ids)}) Searching for model: {model}")
            product_url = run_playwright_search(model, headless=headless_mode)
            if not product_url:
                print(f"[ERROR] No product found for model: {model}")
                continue

            html = fetch_page_data(driver, product_url)
            if not html:
                print(f"[ERROR] Failed to fetch HTML for model: {model}")
                continue

            model_id, title, features, images, manual, category = extract_product_data(html, config_samsung)

            all_data.append({
                "manufacturer": "Samsung",
                "model_id": model_id or model,
                "title": title,
                "category": category,
                "key_features": features,
                "image_urls": images,
                "manual_url": manual,
                "product_url": product_url
            })

            print(f"[SUCCESS] Data extracted for model: {model_id or model}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    save_data_to_json(all_data)
