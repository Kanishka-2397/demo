import os
import json
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright 
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

main_config_path = "A.O.json"
smtp_config_path = "smto_config.json"

with open(main_config_path, 'r') as f:
    config = json.load(f)

with open(smtp_config_path, 'r') as f:
    smtp_config = json.load(f)

BASE_URL = config["base_url"]
BASE_FOLDER = "output"
os.makedirs(BASE_FOLDER, exist_ok=True)

def run_playwright_search(title):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(BASE_URL, timeout=30000)
            page.wait_for_load_state("load")

            click_selector = config["action"]["click"]["selector"]
            fill_selector = config["action"]["fill"]["selector"]
            search_text = config["action"]["fill"]["text"].replace("{{query}}", title)
            result_selector = config["result_selector"]

            page.click(click_selector)
            page.wait_for_timeout(2000)
            visible = page.is_visible(fill_selector)
            if not visible:
                page.evaluate(f'''
                    () => {{
                        const el = document.querySelector("{fill_selector}");
                        if(el) {{
                            let parent = el;
                            while(parent) {{
                                parent.style.display = "block";
                                parent.style.visibility = "visible";
                                parent.style.opacity = 1;
                                parent.removeAttribute("hidden");
                                parent = parent.parentElement;
                            }}
                        }}
                    }}
                ''')
                page.wait_for_timeout(500)
                visible = page.is_visible(fill_selector)
                if not visible:
                    raise Exception(f"Search input '{fill_selector}' still not visible after JS fix")

            page.fill(fill_selector, search_text)
            page.keyboard.press('Enter')
            page.wait_for_selector(result_selector, timeout=10000)
            buttons_count = page.locator(result_selector).count()

            if buttons_count == 0:
                return None

            first_product = page.locator(result_selector).first
            product_url = first_product.get_attribute("data-link")
            if product_url:
                return urljoin(BASE_URL, product_url)
        finally:
            browser.close()

def scrape_product_details(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto(url)
        page.wait_for_load_state("load")
        page.wait_for_timeout(1500)

        data = {}
        for item in config["items"]:
            name = item.get("name")
            selectors = item.get("selectors")
            attr_type = item.get("type", "text")
            match = item.get("match", "first")

            try:
                if match == "all":
                    elements = page.locator(selectors)
                    count = elements.count()
                    values = []
                    for i in range(count):
                        elem = elements.nth(i)
                        if attr_type == "text":
                            values.append(elem.inner_text().strip())
                        else:
                            attr_val = elem.get_attribute(attr_type)
                            if not attr_val:
                                attr_val = elem.inner_text().strip()
                            values.append(attr_val)
                    data[name] = values
                else:
                    element = page.locator(selectors).first
                    if attr_type == "text":
                        data[name] = element.inner_text().strip()
                    else:
                        attr_val = element.get_attribute(attr_type)
                        if not attr_val:
                            attr_val = element.inner_text().strip()
                        data[name] = attr_val
            except Exception as e:
                print(f"[!] Error extracting '{name}': {e}")
                data[name] = None  

        browser.close()
        return data

def save_data_to_file(data, product_title):
    safe_title = "".join(c for c in product_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    filename = f"{safe_title}.json"
    filepath = os.path.join(BASE_FOLDER, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def send_email(product_title, recipient_email, product_data, smtp_cfg):
    msg = MIMEMultipart()
    msg['From'] = smtp_cfg["sender_email"]
    msg['To'] = recipient_email
    msg['Subject'] = f"Scraped Product Data: {product_title}"

    html_content = "<h3>Scraped Product Data</h3><ul>"
    for key, value in product_data.items():
        if isinstance(value, list):
            value = ", ".join(value)
        html_content += f"<li><b>{key}:</b> {value}</li>"
    html_content += "</ul>"

    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP(smtp_cfg["smtp_server"], smtp_cfg["smtp_port"]) as server:
            server.starttls()
            server.login(smtp_cfg["sender_email"], smtp_cfg["password"])
            server.send_message(msg)
            print("[✓] Email sent successfully.")
    except Exception as e:
        print(f"[!] Failed to send email: {e}")

if __name__ == "__main__":
    product_title = "HSE-HAS"
    found_url = run_playwright_search(product_title)

    if found_url:
        details = scrape_product_details(found_url)
        save_data_to_file(details, product_title)
        recipient = smtp_config["recipient_email"]
        send_email(product_title, recipient, details, smtp_config)
