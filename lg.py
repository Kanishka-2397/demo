import os
import sys
import json
import time
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# -------------------- Setup -------------------- #
CONFIG_PATH = r'C:\Users\sarav\Desktop\spiders\config\config.json'
SPIDERS_PATH = r'C:\Users\sarav\Desktop\spiders\spiders\lg.json'
BASE_FOLDER = "output"
os.makedirs(BASE_FOLDER, exist_ok=True)

session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount('http://', adapter)
session.mount('https://', adapter)

# -- Load product config and spider config
if not os.path.exists(CONFIG_PATH):
    print(f"Config file not found: {CONFIG_PATH}")
    sys.exit(1)

if not os.path.exists(SPIDERS_PATH):
    print(f"Spider config file not found: {SPIDERS_PATH}")
    sys.exit(1)

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    products = json.load(f)

with open(SPIDERS_PATH, 'r', encoding='utf-8') as f:
    spider_config = json.load(f)

base_url = spider_config.get("url")
items_config = spider_config.get("items")

# -------------------- Playwright Search -------------------- #
def run_playwright_search(model_id, category, base_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(base_url, timeout=30000)
            page.wait_for_load_state("load")
            print("LG homepage loaded.")

            # Click search button to open search input
            page.click('button[aria-label="Search"]')
            # Fill search input with model_id and category concatenated (space-separated)
            search_text = f"{model_id} {category}"
            page.fill('input[placeholder="Search LG"]', search_text)
            page.press('input[placeholder="Search LG"]', 'Enter')
            page.wait_for_selector('a.css-11xg6yi', timeout=10000)

            first_product = page.locator('a.css-11xg6yi').first
            product_url = first_product.get_attribute("href")
            if product_url:
                full_url = urljoin(base_url, product_url)
                print(f"First product found by Playwright: {full_url}")
                return full_url
            else:
                print("No product URL found by Playwright.")
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
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

    if download_path:
        prefs = {
            "download.default_directory": os.path.abspath(download_path),
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
        }
        chrome_options.add_experimental_option("prefs", prefs)

    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def wait_for_downloads(dir_path, timeout=60):
    for _ in range(timeout):
        if any(f.endswith(".crdownload") for f in os.listdir(dir_path)):
            time.sleep(1)
        else:
            break

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

# -------------------- Fallback Search -------------------- #
def get_first_product_from_fallback(driver, search_url, base_url):
    print(f"🔎 Trying fallback search URL: {search_url}")
    html = fetch_page_data(driver, search_url)
    if not html:
        print("Failed to load fallback search page.")
        return None
    soup = BeautifulSoup(html, "html.parser")
    product_links = soup.select('a.css-11xg6yi')
    if not product_links:
        print("No product links found.")
        return None
    first_link = product_links[0].get("href")
    if not first_link:
        print("First product link has no href.")
        return None
    return urljoin(base_url, first_link)

# -------------------- Extract Product Data -------------------- #
def extract_product_data(html, config_items):
    soup = BeautifulSoup(html, "html.parser")

    def select(selector, attr=None, multi=False):
        elems = soup.select(selector)
        if not elems:
            return [] if multi else ""
        if multi:
            return [el.get(attr) if attr else el.get_text(strip=True) for el in elems]
        return elems[0].get(attr).strip() if attr else elems[0].get_text(strip=True)

    title = select(config_items[0]["selector"])
    features = list(dict.fromkeys(select(config_items[1]["selector"], multi=True)))
    raw_images = select(config_items[2]["selector"], attr="src", multi=True)
    image_urls = [urljoin(base_url, u) for u in raw_images if u and not u.startswith("data:")]
    return title, features, list(set(image_urls))

# -------------------- Download Helpers -------------------- #
def download_images(image_urls, folder, base_url):
    os.makedirs(folder, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}
    for idx, url in enumerate(image_urls):
        full_url = urljoin(base_url, url)
        try:
            img_data = session.get(full_url, headers=headers).content
            with open(os.path.join(folder, f"image_{idx+1}.jpg"), "wb") as f:
                f.write(img_data)
        except Exception as e:
            print(f"[ERROR] Failed to download image {url}: {e}")

def download_manuals_with_pdf(product_url, download_folder):
    os.makedirs(download_folder, exist_ok=True)
    driver = get_selenium_driver(download_folder)
    try:
        driver.get(product_url)
        time.sleep(3)

        support_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/support/product/')]"))
        )
        driver.get(support_button.get_attribute("href"))
        time.sleep(3)

        manual_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Manuals & Software')]"))
        )
        manual_tab.click()
        time.sleep(3)

        icons = driver.find_elements(By.XPATH, "//svg[@data-testid='DocumentScannerOutlinedIcon']") or \
                driver.find_elements(By.XPATH, "//img[@alt='download']")
        for icon in icons:
            btn = icon.find_element(By.XPATH, "./ancestor::div[contains(@class,'MuiBox-root')][1]")
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)

        wait_for_downloads(download_folder)
    except Exception as e:
        print(f"[ERROR] Manual download failed: {e}")
    finally:
        driver.quit()

def get_manual_urls(base_dir, model_id):
    manual_folder = os.path.join(base_dir, f"{model_id}_manuals")
    if not os.path.exists(manual_folder):
        return []
    # Return relative file paths or you can adjust this to return absolute paths or URLs
    return [os.path.join(f"{model_id}_manuals", f) for f in os.listdir(manual_folder) if f.endswith(".pdf")]

# -------------------- Save to JSON -------------------- #
def save_data_to_json(product_data):
    json_path = os.path.join(BASE_FOLDER, "lg_data.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                all_data = json.load(f)
            except json.JSONDecodeError:
                all_data = []
    else:
        all_data = []

    all_data.append(product_data)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2)
    print(f"✅ Product data saved to {json_path}")

# -------------------- Main Script -------------------- #
if __name__ == "__main__":
    for product in products:
        manufacturer = product.get("manufacturer")
        model_id = product.get("model_id", "").strip()
        category = product.get("category", "").strip()
        print(f"\n=== Processing: {manufacturer} | {model_id} | {category} ===")

        product_url = run_playwright_search(model_id, category, base_url)

        if not product_url:
            fallback_search_url = f"{base_url}/search?q={model_id}"
            driver = get_selenium_driver()
            product_url = get_first_product_from_fallback(driver, fallback_search_url, base_url)
            driver.quit()

        if product_url:
            driver = get_selenium_driver()
            html = fetch_page_data(driver, product_url)
            driver.quit()

            if html:
                title, features, image_urls = extract_product_data(html, items_config)
                print(f"Title: {title}")
                print(f"Features: {features}")
                print(f"Image URLs: {image_urls}")

                product_folder = os.path.join(BASE_FOLDER, model_id)
                download_images(image_urls, product_folder, base_url)

                manuals_folder = os.path.join(BASE_FOLDER, f"{model_id}_manuals")
                download_manuals_with_pdf(product_url, manuals_folder)

                manual_files = get_manual_urls(BASE_FOLDER, model_id)

                product_data = {
                    "url": product_url,
                    "title": title,
                    "features": features,
                    "images": image_urls,
                    "manuals": manual_files,
                }
                save_data_to_json(product_data)
        
