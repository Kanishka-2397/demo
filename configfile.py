class LGProductScraper(DownloadsProducts):
    

    def run_playwright_search(self, model_id, category):
        """Use Playwright to search product URL on base_url."""
        base_url = self.config["base_url"]
        action = self.config["action"]
        product_selector = self.config["load"]["product"]["selector"]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(base_url, timeout=30000)
                page.wait_for_load_state("load")

                # Click search icon/button if needed
                page.click(action["click"]["selector"])
                search_text = f"{model_id} {category}"
                page.fill(action["fill"]["selector"], search_text)
                page.press(action["press"]["selector"], 'Enter')

                page.wait_for_selector(product_selector, timeout=10000)
                first_product = page.locator(product_selector).first
                product_url = first_product.get_attribute("href")
                if product_url:
                    product_url = urljoin(base_url, product_url)
                return product_url
            except Exception as e:
                print(f"[ERROR] Playwright search failed: {e}")
                return None
            finally:
                browser.close()


    def get_first_product(self, driver, search_url, base_url):
        """Get first product URL from fallback search page."""
        try:
            driver.get(search_url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.config["load"]["product"]["selector"]))
            )
            first_elem = driver.find_element(By.CSS_SELECTOR, self.config["load"]["product"]["selector"])
            product_url = first_elem.get_attribute("href")
            if product_url:
                return urljoin(base_url, product_url)
            return None
        except Exception as e:
            print(f"[ERROR] Fallback search failed: {e}")
            return None

    def fetch_page_data(self, driver, url):
        """Get HTML source of product page."""
        try:
            driver.get(url)

            # Extract title selector from items config list
            title_selector = next((item["selector"] for item in self.config["items"] if item.get("name") == "title"), None)
            if not title_selector:
                print("[ERROR] Title selector not found in config.")
                return None

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, title_selector))
            )
            time.sleep(2)
            return driver.page_source
        except Exception as e:
            print(f"[ERROR] Fetch page data failed: {e}")
            return None

    def extract_product_data(self, html, items_config):
        """Parse HTML and extract product title, features, images."""
        soup = BeautifulSoup(html, "html.parser")

        title = "N/A"
        features = "N/A"
        images = []

        for item in items_config:
            name = item.get("name")
            selector = item.get("selector")
            if not name or not selector:
                continue

            if name == "title":
                elem = soup.select_one(selector)
                title = elem.get_text(strip=True) if elem else "N/A"

            elif name == "key_features":
                elems = soup.select(selector)
                features_list = [el.get_text(strip=True) for el in elems if el.get_text(strip=True)]
                # Remove duplicates while preserving order
                features = list(dict.fromkeys(features_list))

            elif name == "image_urls":
                for img in soup.select(selector):
                    src = img.get("src") or img.get("data-src")
                    if src:
                        images.append(src)

        return title, features, images




    def download_manuals_with_pdf(self, product_url, download_folder):
        """Download product manuals (PDFs) by navigating the manual/support page."""
        
        driver = self.get_driver(download_folder)
        manuals_cfg = self.config.get("manuals")

        try:
            driver.get(product_url)
            time.sleep(3)

            # Step 1: Navigate to the Support page
            try:
                support_button = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, manuals_cfg["support_bt"]["selector"]))
                )
                support_href = support_button.get_attribute("href")
                if support_href:
                    driver.get(support_href)
                else:
                    driver.execute_script("arguments[0].click();", support_button)
            except TimeoutException:
                print("[ERROR] Support button not found or clickable.")
                return

            time.sleep(3)

            # Step 2: Click the "Manuals & Software" tab
            try:
                manual_tab = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, manuals_cfg["manual_tab"]["selector"]))
                )
                driver.execute_script("arguments[0].click();", manual_tab)
            except TimeoutException:
                print("[ERROR] Manuals & Software tab not found or clickable.")
                return

            time.sleep(3)

            # Step 3: Look for icon (SVG or IMG) that represents the manual PDF
            icon_elem = None
            if "icon_svg" in manuals_cfg:
                try:
                    icon_elem = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, manuals_cfg["icon_svg"]["selector"]))
                    )
                except TimeoutException:
                    pass  # fallback to image

            if not icon_elem and "icon_img" in manuals_cfg:
                try:
                    icon_elem = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, manuals_cfg["icon_img"]["selector"]))
                    )
                except TimeoutException:
                    pass

            if not icon_elem:
                print("[WARN] Manual download icon not found.")
                return

            # Step 4: Find clickable parent (anchor, button, or role='button' div)
            button_elem = None
            for xpath in ["./ancestor::a", "./ancestor::button", "./ancestor::div[@role='button']"]:
                try:
                    button_elem = icon_elem.find_element(By.XPATH, xpath)
                    if button_elem:
                        break
                except NoSuchElementException:
                    continue

            if not button_elem:
                print("[WARN] Clickable manual download button not found.")
                return

            # Scroll into view
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button_elem)

            # Step 5: Ensure it's clickable
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: button_elem.is_enabled() and button_elem.is_displayed()
                )
            except TimeoutException:
                print("[WARN] Manual download button not clickable after wait.")
                return

            # Step 6: Click to trigger PDF download
            try:
                ActionChains(driver).move_to_element(button_elem).click().perform()
            except (ElementClickInterceptedException, Exception) as e:
                print(f"[WARN] ActionChains click failed: {e}, trying JS click")
                try:
                    driver.execute_script("arguments[0].click();", button_elem)
                except Exception as e2:
                    print(f"[ERROR] JS click also failed: {e2}")
                    return

            # Step 7: Wait for the file to download
            self.wait_for_downloads(download_folder)

        finally:
            time.sleep(5)  # give it a little buffer to finalize download
            driver.quit()


    def wait_for_downloads(self, folder, timeout=60):
        """Wait for all downloads to complete in folder."""
        seconds = 0
        while seconds < timeout:
            files = os.listdir(folder)
            # If any files still have the .crdownload extension (Chrome's temp download)
            if any(f.endswith(".crdownload") for f in files):
                time.sleep(1)
                seconds += 1
            # If at least one PDF exists, assume download finished
            elif any(f.lower().endswith(".pdf") for f in files):
                break
            else:
                break
        else:
            print("[WARNING] Timeout waiting for downloads to finish.")

    def get_manual_urls(self, manuals_folder):
        """Return list of manual PDF file paths inside manual folder."""
        if not os.path.exists(manuals_folder):
            return []
        return [os.path.abspath(os.path.join(manuals_folder, f))
                for f in os.listdir(manuals_folder) if f.lower().endswith(".pdf")]




class WhirlpoolProductScraper(DownloadsProducts):

    # Instance method because it uses self.config
    def run_playwright_search(self, model_id, category, base_url):
        config = self.config
        base_url = config.get("base_url", base_url)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()

            page.goto(base_url, timeout=60000)
            print("Homepage loaded.")

            # Handle modal actions (click close buttons)
            for action in config.get("actions", []):
                if action.get("type") == "click" and action.get("name") == "modals":
                    for selector in action.get("selectors", []):
                        try:
                            locator = page.locator(f"xpath={selector}" if selector.startswith("//") else selector)
                            if locator.count() > 0 and locator.first.is_visible():
                                locator.first.click()
                                print(f"Closed modal: {selector}")
                                time.sleep(1)
                                break  # Close only first matched modal
                        except Exception:
                            pass  # Ignore modal errors

            # Find search input and fill
            search_action = next((a for a in config.get("actions", []) if a.get("name") == "search_input"), None)
            if not search_action:
                print("[ERROR] Search input config missing.")
                browser.close()
                return None

            search_selector = search_action["selector"]
            search_input = page.locator(search_selector).first
            search_input.wait_for(state="visible", timeout=15000)
            search_input.fill(f"{model_id} {category}".strip())
            search_input.press("Enter")
            print(f"Search performed for model ID: {model_id}")
            page.wait_for_load_state("load", timeout=60000)

            # Find product items
            product_items_cfg = next((l for l in config.get("locations", []) if l.get("name") == "product_items"), None)
            if not product_items_cfg:
                print("[ERROR] Product items config missing.")
                browser.close()
                return None

            product_items = page.locator(product_items_cfg["selector"])
            count = product_items.count()

            if count == 0:
                print("[ERROR] No product items found.")
                browser.close()
                return None

            # Find matching SKU attribute name
            sku_attr_cfg = next((a for a in config.get("attributes", []) if a.get("name") == "product_sku"), None)
            sku_attr = sku_attr_cfg["attribute"] if sku_attr_cfg else "data-product-sku"

            # Search for product with matching SKU
            for i in range(count):
                sku = product_items.nth(i).get_attribute(sku_attr)
                if sku and model_id.lower() in sku.lower():
                    link = product_items.nth(i).locator("a").first
                    href = link.get_attribute("href")
                    if href:
                        full_url = urljoin(base_url, href)
                        browser.close()
                        return full_url

            # Fallback: return first product href
            fallback_link = product_items.first.locator("a").first.get_attribute("href")
            browser.close()
            return urljoin(base_url, fallback_link) if fallback_link else None


    # -------------------- Data Extraction -------------------- #

    @staticmethod
    def extract_background_image_url(style_attr):
        import re
        match = re.search(r'url\(["\']?(.*?)["\']?\)', style_attr)
        return match.group(1) if match else None

    @staticmethod
    def extract_product_data(html, config, base_url):
        from bs4 import BeautifulSoup
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
                # Remove duplicates
                return list(set(results))
            else:
                el = elements[0]
                return urljoin(base_url, el[attr]) if attr and el.has_attr(attr) else el.get_text(strip=True)

        # Extract title
        title = select_data(config["items"][0]["selector"])

        key_features = []

        kf_elem = soup.select_one(config["items"][1]["selector"])
        if kf_elem:
            lis = kf_elem.find_all("li")
            if lis:
                # Extract and clean <li> contents
                key_features = [
                    li.get_text(strip=True)
                    for li in lis
                    if li.get_text(strip=True) and li.get_text(strip=True) != "•"
                ]
            else:
                # Fallback: clean pipe-separated text
                raw = kf_elem.get_text(separator="|", strip=True)
                key_features = [
                    text.strip()
                    for text in raw.split("|")
                    if text.strip() and text.strip() != "•"
                ]

        # Extract image URLs
        image_urls = select_data(
            config["items"][2]["selector"],
            match=config["items"][2].get("match", "all"),
            attr=config["items"][2].get("type")
        )
        if not isinstance(image_urls, list):
            image_urls = [image_urls] if image_urls else []

        # Also extract background images from div.s7thumb style attribute
        for div in soup.select("div.s7thumb"):
            url = WhirlpoolProductScraper.extract_background_image_url(div.get("style", ""))
            if url:
                image_urls.append(urljoin(base_url, url))

        # Extract manual PDF URL
        manual_url = select_data(
            config["items"][3]["selector"],
            match=config["items"][3].get("match", "first"),
            attr=config["items"][3].get("type")
        )

        # Fallback for manual URL
        if not manual_url:
            pdfs = [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True) if a["href"].endswith(".pdf")]
            manuals = [p for p in pdfs if "manual" in p.lower()]
            manual_url = manuals[0] if manuals else (pdfs[0] if pdfs else "")

        return title, key_features, image_urls, manual_url
