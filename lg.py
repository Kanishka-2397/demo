import os
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
from config import config_lg

# -------------------- Setup -------------------- #
BASE_FOLDER = "lg_download"
os.makedirs(BASE_FOLDER, exist_ok=True)

session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount('http://', adapter)
session.mount('https://', adapter)

# -------------------- Playwright Search -------------------- #
def run_playwright_search(product):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(config_lg["url"], timeout=30000)
            page.wait_for_load_state("load")
            print("✅ LG homepage loaded.")

            page.click('button[aria-label="Search"]')
            page.fill('input[placeholder="Search LG"]', product)
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
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
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
def get_first_product_from_fallback(driver, search_url):
    print(f"🔎 Trying fallback search URL: {search_url}")
    html = fetch_page_data(driver, search_url)
    if not html:
        print("❌ Failed to load fallback search page.")
        return None
    soup = BeautifulSoup(html, "html.parser")
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
                val = el.get(attr) if attr else el.get_text(strip=True)
                if val:
                    results.append(val.strip())
            return results
        el = elems[0]
        return el.get(attr).strip() if attr else el.get_text(strip=True)

    title = select(config["items"][0]["selector"])
    key_features = select(config["items"][1]["selector"], multi=True)
    detailed_features = select(config["items"][2]["selector"], multi=True)
    features = list(dict.fromkeys(key_features + detailed_features))
    raw_images = select(config["items"][3]["selector"], attr="src", multi=True)
    image_urls = [urljoin(config_lg["url"], u) for u in raw_images if u and not u.startswith("data:")]
    return title, features, list(set(image_urls))

# -------------------- Download Helpers -------------------- #
def download_images(image_urls, folder, base_url):
    os.makedirs(folder, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}
    for idx, url in enumerate(image_urls):
        full_url = urljoin(base_url, url)
        img_data = session.get(full_url, headers=headers).content
        with open(os.path.join(folder, f"image_{idx+1}.jpg"), "wb") as f:
            f.write(img_data)

def download_manuals_with_pdf(product_url, download_folder):
    os.makedirs(download_folder, exist_ok=True)
    driver = get_selenium_driver(download_folder)
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
    driver.quit()

def get_manual_urls(base_dir, model_id):
    manual_folder = os.path.join(base_dir, f"{model_id}_manuals")
    if not os.path.exists(manual_folder):
        return []
    return [f"{model_id}_manuals/{f}" for f in os.listdir(manual_folder) if f.endswith(".pdf")]

def update_json_manuals(json_file_path, base_dir):
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for item in data:
        model_id = item['product_url'].split('/')[-1]
        item['manual_urls'] = get_manual_urls(base_dir, model_id)
    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

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

# -------------------- Main Script -------------------- #
if __name__ == "__main__":
    model_id = input("Enter LG model ID (e.g., LRYKC2606S): ").strip()
    categotry = input("Enter LG category(e.g, refrigerator):")
    manufacturer = input("Enter your band(e.g, LG,WHRILPOOL,SAMSUNG):")
    product_url = run_playwright_search(model_id)

    if not product_url:
        fallback_url = f"{config_lg['url']}/search?q={model_id}"
        driver = get_selenium_driver()
        product_url = get_first_product_from_fallback(driver, fallback_url)
        driver.quit()

    if product_url:
        driver = get_selenium_driver()
        html = fetch_page_data(driver, product_url)
        driver.quit()

        if html:
            title, features, image_urls = extract_product_data(html, config_lg)
            product_folder = os.path.join(BASE_FOLDER, model_id)
            manual_folder = os.path.join(BASE_FOLDER, f"{model_id}_manuals")

            download_images(image_urls, product_folder, config_lg["url"])
            download_manuals_with_pdf(product_url, manual_folder)

            product_data = {
                
                "title": title,
                "features": features,
                "images": image_urls,
                "manual_urls": get_manual_urls(BASE_FOLDER, model_id),
                "product_url": product_url
            }
            save_data_to_json(product_data)

        save_data_to_json(product_data)

    finally:
        driver.quit()
