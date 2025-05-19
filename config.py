import json
config_lg = {
    "url": "https://www.lg.com/us/",
    "fallback_urls": {
        "default": "https://www.lg.com/us/search?q={model_id}&tab=product",
        "category_url": "https://www.lg.com/us/search?q={model_id}%20category&tab=product",
        "key_url": "https://www.lg.com/us/search?q={model_id}%20keyfeatures&tab=product",
        "image_url": "https://www.lg.com/us/search?q={model_id}%20images&tab=product",
        "manual_url": "https://www.lg.com/us/support/product/lg-{model_id}",
    },
    "items": [
        {
            "name": "model_id",
            "selector": "span.MuiTypography-root.MuiTypography-overline.css-rrulv7",
            "match": "first",
            "type": "text"
        },
        {
            "name": "title",
            "selector": "h2.MuiTypography-root.MuiTypography-h5.css-72m7wz",
            "match": "first",
            "type": "text"
        },
        {
            "name": "breadcrumb",
            "selector": "ol.MuiBreadcrumbs-ol > li",
            "match": "first",
            "type": "text"
        },
        {
            "name": "key_features",
            "selector": "ul.css-1he9hsx li",
            "match": "first",
            "type": "text"
        },
        {
            "name": "detailed_features",
            "selector": "div.css-1qtv6i2 li",
            "match": "first",
            "type": "text"
        },
        {
            "name": "image_urls",
            "selector": "img",
            "match": "all",
            "type": "src"
        },
        {
            "name": "manual_urls",
            "selector": "a[href$='.pdf']",
            "match": "all",
            "type": "link"
        }
    ]
}


# Whirlpool Configuration
config_whirlpool = {
    "url": "https://www.whirlpool.com",
    "fallback_urls": {
        "category_url": "https://www.whirlpool.com/results.html?term={model_id}+category",
        "image_url": "https://www.whirlpool.com/results.html?term={model_id}+images",
        "key_url": "https://www.whirlpool.com/results.html?term={model_id}+keyfeatures",
    },
    "items": [
        {
            "name": "model_id",
            "selector": "span.pdp-tray-model-code",
            "match": "first",
            "type": "text"
        },
        {
            "name": "title",
            "selector": "span.product-title",
            "match": "first",
            "type": "text"
        },
        {
            "name": "key_features",
            "selector": "div.pdp-tray-key-features-list",
            "match": "all",
            "type": "text"
        },
        {
            "name": "image_urls",
            "selector": "img.product-image",
            "match": "all",
            "type": "src"
        },
        {
            "name": "manual_pdf_url",
            "selector": "a[href$='.pdf']",
            "match": "first",
            "type": "href"
        },
        {
            "name": "category",
            "selector": "ul.breadcrumbs li span[itemprop='name']",
            "match": "first",
            "type": "text"
        }
    ]
}


# Samsung Configuration
config_samsung = {
    "url": "https://www.samsung.com/us",
    "fall_url": {
        "features_url": "https://www.samsung.com/us/search/searchMain/?listType=g&searchTerm={model_id}+keyfeatures&size=9",
        "image_url": "https://www.samsung.com/us/search/searchMain/?listType=g&searchTerm={model_id}+images&size=9",
        "category_url": "https://www.samsung.com/us/search/searchMain/?listType=g&searchTerm={model_id}+category&size=9"
    },
    "items": [
        {
            "name": "model_id",
            "selector": ".ModelInfo_modalInfo__Dlls0 span",
            "match": "first",
            "type": "text"
        },
        {
            "name": "title",
            "selector": "div.ProductTitle_product__KGKRj h1",
            "match": "first",
            "type": "text"
        },
        {
            "name": "icon_features",
            "selector": ".ProductDetailsBadge_badge__wInap",
            "match": "all",
            "type": "text"
        },
        {
            "name": "detailed_features",
            "selector": ".ProductSummary_detailList__3pjAV",
            "match": "all",
            "type": "text"
        },
        {
            "name": "key_features",
            "selector": ".KeyFeatures_cards__V77Wy > div",
            "match": "all",
            "type": "text"
        },
        {
            "name": "images",
            "selector": "img[src*='samsung.com']",
            "match": "all",
            "type": "src"
        },
        {
            "name": "breadcrumb",
            "selector": ".Breadcrumb_breadcrumbText__WEmi6",
            "match": "all",
            "type": "text"
        },
        {
            "name": "pdf_url",
            "selector": "a[href$='.pdf']",
            "match": "all",
            "type": "href"
        }
    ]
}



def get_config(load_from_file=False, brand=None):
    if load_from_file:
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                return config.get(brand, {}) if brand else config
        except FileNotFoundError:
            print("Config file not found, returning default LG config.")
            return config_lg

    # Return the appropriate default config
    if brand == "whirlpool":
        return config_whirlpool
    elif brand == "samsung":
        return config_samsung
    return config_lg  # Default to LG


def generate_config(brand="lg"):
    brand = brand.lower()
    config_map = {
        "lg": config_lg,
        "whirlpool": config_whirlpool,
        "samsung": config_samsung
    }

    config_to_save = config_map.get(brand)
    if config_to_save:
        with open("config.json", "w") as f:
            json.dump({brand: config_to_save}, f, indent=4)
            print(f"Configuration for '{brand}' saved to config.json.")
    else:
        print(f"No configuration found for brand: {brand}")
