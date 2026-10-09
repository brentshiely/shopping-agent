#!/usr/bin/env python3
"""
Shop Crawl — Grocery Price Comparison
======================================
Uses Playwright (real Chromium browser) to fetch store pages,
bypassing bot-detection that blocks plain HTTP requests.

Usage:
    python3 crawler.py

Output:
    dashboard.html  — open in any browser
"""

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup
import json, re, time, os, sys
from datetime import datetime
import urllib.parse

# ── Items to track ────────────────────────────────────────────────────────────
ITEMS = [
    {
        "id":         "diet_mtn_dew",
        "name":       "Diet Mountain Dew",
        "note":       "Cans, 24 or 30 pack — best $/fl oz",
        "unit_label": "fl oz",
        "filter":     {"require": ["dew"], "reject": []},
        "queries": {
            "walmart":   "diet mountain dew 24 pack cans",
            "costco":    "diet mountain dew 24 pack",
            "cub":       "diet mountain dew 24 pack cans",
            "hyvee":     "diet mountain dew 24 pack",
            "lunds":     "diet mountain dew 24 pack",
            "aldi":      "diet mountain dew 24 pack",
            "target":    "diet mountain dew 24 pack cans",
            "kowalskis": "diet mountain dew 24 pack",
            "walgreens": "diet mountain dew 24 pack cans",
        },
    },
    {
        "id":         "hazelnut_coffee",
        "name":       "Hazelnut Coffee (Ground)",
        "note":       "Any brand — best $/oz",
        "unit_label": "oz",
        "filter":     {"require": ["hazelnut", "coffee"], "reject": ["creamer", "syrup", "k-cup", "pod", "capsule", "liquid"]},
        "queries": {
            "walmart":   "great value hazelnut ground coffee",
            "costco":    "kirkland hazelnut coffee ground",
            "cub":       "eight o'clock hazelnut ground coffee",
            "hyvee":     "hazelnut ground coffee",
            "lunds":     "hazelnut ground coffee",
            "aldi":      "hazelnut ground coffee",
            "target":    "hazelnut ground coffee",
            "kowalskis": "hazelnut ground coffee",
            "walgreens": "hazelnut ground coffee",
        },
    },
    {
        "id":         "carmex_jars",
        "name":       "Carmex Lip Balm Jars",
        "note":       "3-pack, original — best $/oz",
        "unit_label": "oz",
        "filter":     {"require": ["carmex"], "reject": []},
        "queries": {
            "walmart":   "carmex lip balm jar 3 pack",
            "costco":    "carmex lip balm jar 3 pack",
            "cub":       "carmex lip balm jar 3 pack",
            "hyvee":     "carmex lip balm jar 3 pack",
            "lunds":     "carmex lip balm jar 3 pack",
            "aldi":      "carmex lip balm jar 3 pack",
            "target":    "carmex lip balm jar 3 pack",
            "kowalskis": "carmex lip balm jar 3 pack",
            "walgreens": "carmex lip balm jar 3 pack",
        },
    },
    {
        "id":         "sprayway_glass_cleaner",
        "name":       "Sprayway Glass Cleaner",
        "note":       "Aerosol, 19 oz — best $/oz",
        "unit_label": "oz",
        "filter":     {"require": ["glass", "clean"], "reject": ["toilet", "bowl", "bathroom", "shower", "tub", "drain"]},
        "queries": {
            "walmart":   "sprayway glass cleaner aerosol 19 oz",
            "costco":    "sprayway glass cleaner",
            "cub":       "sprayway glass cleaner 19 oz",
            "hyvee":     "sprayway glass cleaner 19 oz",
            "lunds":     "sprayway glass cleaner 19 oz",
            "aldi":      "sprayway glass cleaner 19 oz",
            "target":    "sprayway glass cleaner 19 oz",
            "kowalskis": "sprayway glass cleaner 19 oz",
            "walgreens": "sprayway glass cleaner 19 oz",
        },
    },
    {
        "id":         "nyquil",
        "name":       "NyQuil / Nighttime Cold & Flu",
        "note":       "NyQuil or generic equivalent — best $/fl oz",
        "unit_label": "fl oz",
        "filter":     {"require": ["cold", "flu"], "reject": ["daytime", "day", "sinus", "children", "child", "kids"]},
        "queries": {
            "walmart":   "equate nighttime cold flu liquid",
            "costco":    "nyquil cold flu nighttime",
            "cub":       "nyquil cold flu nighttime liquid",
            "hyvee":     "nyquil cold flu nighttime liquid",
            "lunds":     "nyquil cold flu nighttime liquid",
            "aldi":      "nyquil cold flu nighttime",
            "target":    "up up nighttime cold flu liquid",
            "kowalskis": "nyquil cold flu nighttime liquid",
            "walgreens": "walgreens nighttime cold flu liquid",
        },
    },
]

# ── Store configs ─────────────────────────────────────────────────────────────
STORES = [
    {"id": "walmart",   "name": "Walmart",        "color": "#0071CE", "light": "#E8F4FD"},
    {"id": "costco",    "name": "Costco",          "color": "#E31837", "light": "#FDECEA"},
    {"id": "cub",       "name": "Cub Foods",       "color": "#A50000", "light": "#FFF0F0"},
    {"id": "hyvee",     "name": "HyVee",           "color": "#CC0033", "light": "#FFF0F3"},
    {"id": "lunds",     "name": "Lunds & Byerlys", "color": "#2D6A4F", "light": "#EBF5EE"},
    {"id": "aldi",      "name": "Aldi",            "color": "#1565C0", "light": "#E3F2FD"},
    {"id": "target",    "name": "Target",          "color": "#CC0000", "light": "#FFEBEE"},
    {"id": "kowalskis", "name": "Kowalski's",      "color": "#5D4037", "light": "#EFEBE9"},
    {"id": "walgreens", "name": "Walgreens",       "color": "#E31837", "light": "#FDECEA"},
]
STORE_MAP = {s["id"]: s for s in STORES}

# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_price(text: str):
    """Extract a dollar amount from text."""
    if not text:
        return None
    text = str(text).replace(",", "")
    m = re.search(r"\$\s*([\d]+\.?\d*)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d]+\.\d{2})", text)
    if m:
        return float(m.group(1))
    return None


def parse_size_oz(text: str):
    """
    Return total oz (or fl oz) from a product name/description.
    Handles patterns like:
      "24 pack, 12 fl oz cans"   → 24 × 12 = 288
      "12 oz bag"                → 12
      "2 lb (32 oz)"             → 32
    """
    t = str(text)
    pack   = re.search(r"(\d+)\s*[-–]?\s*(?:pack|pk|ct|count|cans?)\b", t, re.I)
    fluid  = re.search(r"(\d+\.?\d*)\s*fl\.?\s*oz", t, re.I)
    weight = re.search(r"(\d+\.?\d*)\s*oz\b(?!\s*can)", t, re.I)
    lbs    = re.search(r"(\d+\.?\d*)\s*lb\b", t, re.I)

    if pack and fluid:
        return int(pack.group(1)) * float(fluid.group(1))
    if fluid:
        return float(fluid.group(1))
    if weight:
        return float(weight.group(1))
    if lbs:
        return float(lbs.group(1)) * 16
    return None


def passes_filter(name: str, item_filter: dict) -> bool:
    """Return True only if product name passes require/reject keyword checks."""
    if not item_filter:
        return True
    n = name.lower()
    for word in item_filter.get("require", []):
        if word.lower() not in n:
            return False
    for word in item_filter.get("reject", []):
        if word.lower() in n:
            return False
    return True


def best_pick(results: list):
    """Return the entry with the lowest price_per_oz (or lowest price if no size info)."""
    if not results:
        return None
    with_ppo = [r for r in results if r.get("price_per_oz")]
    if with_ppo:
        return min(with_ppo, key=lambda r: r["price_per_oz"])
    with_price = [r for r in results if r.get("price")]
    if with_price:
        return min(with_price, key=lambda r: r["price"])
    return None


def search_url_for(store_id: str, query: str) -> str:
    """Fallback search URL for each store."""
    q = urllib.parse.quote(query)
    urls = {
        "walmart":   f"https://www.walmart.com/search?q={q}",
        "costco":    f"https://www.costco.com/CatalogSearch?dept=All&keyword={q}",
        "cub":       f"https://www.cub.com/search?q={q}",
        "hyvee":     f"https://www.hy-vee.com/search?q={q}",
        "lunds":     f"https://www.lundsandbyerlys.com/search?q={q}",
        "aldi":      f"https://new.aldi.us/results?q={q}",
        "target":    f"https://www.target.com/s?searchTerm={q}",
        "kowalskis": f"https://www.kowalskis.com/search?q={q}",
        "walgreens": f"https://www.walgreens.com/search/results.jsp?Ntt={q}",
    }
    return urls.get(store_id, "#")


# ── Page fetcher ──────────────────────────────────────────────────────────────
def get_html(page, url: str, wait_sel: str = None, extra_ms: int = 2000) -> str:
    """Navigate with Playwright and return fully-rendered HTML."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if wait_sel:
            try:
                page.wait_for_selector(wait_sel, timeout=8000)
            except PWTimeout:
                pass  # use whatever loaded
        page.wait_for_timeout(extra_ms)
        return page.content()
    except Exception as e:
        print(f"      ⚠️  {e}")
        return ""


# ── Scrapers ──────────────────────────────────────────────────────────────────
def scrape_walmart(page, query: str, n: int = 6) -> list:
    url = f"https://www.walmart.com/search?q={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel="script#__NEXT_DATA__")
        soup = BeautifulSoup(html, "lxml")
        tag  = soup.find("script", id="__NEXT_DATA__")
        if not tag:
            print("    [walmart] __NEXT_DATA__ not found")
            return []
        data   = json.loads(tag.string)
        stacks = (data.get("props", {})
                      .get("pageProps", {})
                      .get("initialData", {})
                      .get("searchResult", {})
                      .get("itemStacks", []))
        items = []
        for s in stacks:
            items.extend(s.get("items", []))
        for item in items[:n]:
            name  = item.get("name", "")
            pi    = item.get("priceInfo", {})
            price = (pi.get("currentPrice", {}).get("price")
                     or pi.get("linePrice")
                     or (pi.get("wasPrice") or {}).get("price"))
            if not (name and price):
                continue
            href = item.get("canonicalUrl", "")
            size = parse_size_oz(name)
            out.append({
                "store":        "walmart",
                "name":         name[:100],
                "price":        float(price),
                "size_oz":      size,
                "price_per_oz": round(float(price) / size, 4) if size else None,
                "url":          f"https://www.walmart.com{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [walmart] {e}")
    return out


def scrape_costco(page, query: str, n: int = 6) -> list:
    url = f"https://www.costco.com/CatalogSearch?dept=All&keyword={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel=".product-list-item", extra_ms=2500)
        soup = BeautifulSoup(html, "lxml")
        products = (soup.select(".product-list-item")
                    or soup.select('[automation-id="product-list"] li')
                    or soup.select(".product-grid-product"))
        for product in products[:n]:
            name_el  = product.select_one(".description a, .product-title a, h2 a")
            price_el = product.select_one(
                ".price .value, .your-price .value, "
                "[automation-id='product-price'] .value, .final-price"
            )
            link_el  = product.select_one("a[href]")
            name  = name_el.get_text(strip=True)    if name_el  else None
            price = parse_price(price_el.get_text()) if price_el else None
            href  = link_el["href"]                  if link_el  else url
            if not (name and price):
                continue
            size = parse_size_oz(name)
            out.append({
                "store":        "costco",
                "name":         name[:100],
                "price":        price,
                "size_oz":      size,
                "price_per_oz": round(price / size, 4) if size else None,
                "url":          href if href.startswith("http") else f"https://www.costco.com{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [costco] {e}")
    return out


def scrape_cub(page, query: str, n: int = 6) -> list:
    url = f"https://www.cub.com/search?q={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel="[data-testid='product-card'], .product-card", extra_ms=2500)
        soup = BeautifulSoup(html, "lxml")
        selectors = [
            "[data-testid='product-card']",
            ".product-card",
            ".product-cell",
            "li.grid-cell",
        ]
        products = []
        for sel in selectors:
            products = soup.select(sel)
            if products:
                break
        for product in products[:n]:
            name_el  = product.select_one(
                "[data-testid='product-title'], .product-name, .title, h3, h4"
            )
            price_el = product.select_one(
                "[data-testid='product-price'], .product-price, .price, [class*='price']"
            )
            link_el  = product.select_one("a[href]")
            name  = name_el.get_text(strip=True)    if name_el  else None
            price = parse_price(price_el.get_text()) if price_el else None
            href  = link_el.get("href", "")          if link_el  else ""
            if not (name and price):
                continue
            size = parse_size_oz(name)
            out.append({
                "store":        "cub",
                "name":         name[:100],
                "price":        price,
                "size_oz":      size,
                "price_per_oz": round(price / size, 4) if size else None,
                "url":          href if href.startswith("http") else f"https://www.cub.com{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [cub] {e}")
    return out


def scrape_hyvee(page, query: str, n: int = 6) -> list:
    url = f"https://www.hy-vee.com/search?q={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel=".product-card, [data-testid='product']", extra_ms=3000)
        soup = BeautifulSoup(html, "lxml")
        selectors = [
            ".product-card",
            "[data-testid='product']",
            ".product-item",
            ".search-result-item",
        ]
        products = []
        for sel in selectors:
            products = soup.select(sel)
            if products:
                break
        for product in products[:n]:
            name_el  = product.select_one(".product-name, [data-testid='product-name'], h3, h4, .name")
            price_el = product.select_one(".product-price, [data-testid='price'], .price, [class*='price']")
            link_el  = product.select_one("a[href]")
            name  = name_el.get_text(strip=True)    if name_el  else None
            price = parse_price(price_el.get_text()) if price_el else None
            href  = link_el.get("href", "")          if link_el  else ""
            if not (name and price):
                continue
            size = parse_size_oz(name)
            out.append({
                "store":        "hyvee",
                "name":         name[:100],
                "price":        price,
                "size_oz":      size,
                "price_per_oz": round(price / size, 4) if size else None,
                "url":          href if href.startswith("http") else f"https://www.hy-vee.com{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [hyvee] {e}")
    return out


def scrape_lunds(page, query: str, n: int = 6) -> list:
    url = f"https://www.lundsandbyerlys.com/search?q={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel=".product-card, .product-item", extra_ms=2500)
        soup = BeautifulSoup(html, "lxml")
        selectors = [
            ".product-card",
            ".product-item",
            "[data-testid='product']",
            ".item-cell",
        ]
        products = []
        for sel in selectors:
            products = soup.select(sel)
            if products:
                break
        for product in products[:n]:
            name_el  = product.select_one(".product-name, .title, h3, h4, .name")
            price_el = product.select_one(".product-price, .price, [class*='price']")
            link_el  = product.select_one("a[href]")
            name  = name_el.get_text(strip=True)    if name_el  else None
            price = parse_price(price_el.get_text()) if price_el else None
            href  = link_el.get("href", "")          if link_el  else ""
            if not (name and price):
                continue
            size = parse_size_oz(name)
            out.append({
                "store":        "lunds",
                "name":         name[:100],
                "price":        price,
                "size_oz":      size,
                "price_per_oz": round(price / size, 4) if size else None,
                "url":          href if href.startswith("http") else f"https://www.lundsandbyerlys.com{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [lunds] {e}")
    return out


def scrape_aldi(page, query: str, n: int = 6) -> list:
    url = f"https://new.aldi.us/results?q={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel=".product-tile, [data-testid='product-tile']", extra_ms=2500)
        soup = BeautifulSoup(html, "lxml")
        selectors = [
            ".product-tile",
            "[data-testid='product-tile']",
            ".plp-product-tile",
        ]
        products = []
        for sel in selectors:
            products = soup.select(sel)
            if products:
                break
        for product in products[:n]:
            name_el  = product.select_one(".product-tile__name, .product-name, h3, h4")
            price_el = product.select_one(".product-tile__price, .base-price, [class*='price']")
            link_el  = product.select_one("a[href]")
            name  = name_el.get_text(strip=True)    if name_el  else None
            price = parse_price(price_el.get_text()) if price_el else None
            href  = link_el.get("href", "")          if link_el  else ""
            if not (name and price):
                continue
            size = parse_size_oz(name)
            out.append({
                "store":        "aldi",
                "name":         name[:100],
                "price":        price,
                "size_oz":      size,
                "price_per_oz": round(price / size, 4) if size else None,
                "url":          href if href.startswith("http") else f"https://new.aldi.us{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [aldi] {e}")
    return out


def scrape_target(page, query: str, n: int = 6) -> list:
    url = f"https://www.target.com/s?searchTerm={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel="[data-test='product-details'], [class*='ProductCard']", extra_ms=3000)
        soup = BeautifulSoup(html, "lxml")
        selectors = [
            "[data-test='product-details']",
            ".ProductCardVariantDefault",
            "[class*='ProductCard']",
        ]
        products = []
        for sel in selectors:
            products = soup.select(sel)
            if products:
                break
        for product in products[:n]:
            name_el  = product.select_one("[data-test='product-title'], a[data-test='product-title'], h3, .product-title")
            price_el = product.select_one("[data-test='current-price'], [class*='CurrentPrice'], [class*='price']")
            link_el  = product.select_one("a[href*='/p/']")
            name  = name_el.get_text(strip=True)    if name_el  else None
            price = parse_price(price_el.get_text()) if price_el else None
            href  = link_el.get("href", "")          if link_el  else ""
            if not (name and price):
                continue
            size = parse_size_oz(name)
            out.append({
                "store":        "target",
                "name":         name[:100],
                "price":        price,
                "size_oz":      size,
                "price_per_oz": round(price / size, 4) if size else None,
                "url":          href if href.startswith("http") else f"https://www.target.com{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [target] {e}")
    return out


def scrape_kowalskis(page, query: str, n: int = 6) -> list:
    url = f"https://www.kowalskis.com/search?q={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel=".product-card, .product-item", extra_ms=2500)
        soup = BeautifulSoup(html, "lxml")
        selectors = [
            ".product-card",
            ".product-item",
            "[data-testid='product']",
        ]
        products = []
        for sel in selectors:
            products = soup.select(sel)
            if products:
                break
        for product in products[:n]:
            name_el  = product.select_one(".product-name, .title, h3, h4")
            price_el = product.select_one(".product-price, .price, [class*='price']")
            link_el  = product.select_one("a[href]")
            name  = name_el.get_text(strip=True)    if name_el  else None
            price = parse_price(price_el.get_text()) if price_el else None
            href  = link_el.get("href", "")          if link_el  else ""
            if not (name and price):
                continue
            size = parse_size_oz(name)
            out.append({
                "store":        "kowalskis",
                "name":         name[:100],
                "price":        price,
                "size_oz":      size,
                "price_per_oz": round(price / size, 4) if size else None,
                "url":          href if href.startswith("http") else f"https://www.kowalskis.com{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [kowalskis] {e}")
    return out


def scrape_walgreens(page, query: str, n: int = 6) -> list:
    url = f"https://www.walgreens.com/search/results.jsp?Ntt={urllib.parse.quote(query)}"
    out = []
    try:
        html = get_html(page, url, wait_sel=".product-name, [data-testid='product-card']", extra_ms=2500)
        soup = BeautifulSoup(html, "lxml")
        selectors = [
            ".product-name",
            "[data-testid='product-card']",
            ".product-list__item",
            ".search-result-productname",
        ]
        products = []
        for sel in selectors:
            products = soup.select(sel)
            if products:
                break
        for product in products[:n]:
            name_el  = product.select_one(".product-name a, .product-title, h3, h4, a")
            price_el = product.select_one(".product-price, .price, [class*='price']")
            link_el  = product.select_one("a[href]")
            name  = name_el.get_text(strip=True)    if name_el  else None
            price = parse_price(price_el.get_text()) if price_el else None
            href  = link_el.get("href", "")          if link_el  else ""
            if not (name and price):
                continue
            size = parse_size_oz(name)
            out.append({
                "store":        "walgreens",
                "name":         name[:100],
                "price":        price,
                "size_oz":      size,
                "price_per_oz": round(price / size, 4) if size else None,
                "url":          href if href.startswith("http") else f"https://www.walgreens.com{href}",
                "search_url":   url,
            })
    except Exception as e:
        print(f"    [walgreens] {e}")
    return out


SCRAPERS = {
    "walmart":   scrape_walmart,
    "costco":    scrape_costco,
    "cub":       scrape_cub,
    "hyvee":     scrape_hyvee,
    "lunds":     scrape_lunds,
    "aldi":      scrape_aldi,
    "target":    scrape_target,
    "kowalskis": scrape_kowalskis,
    "walgreens": scrape_walgreens,
}


# ── HTML Generation ───────────────────────────────────────────────────────────
def generate_dashboard(all_data: dict, timestamp: str) -> str:
    stores_js  = json.dumps(STORES)
    items_js   = json.dumps(ITEMS)
    results_js = json.dumps(all_data)
    ts_js      = json.dumps(timestamp)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shop Crawl — Price Comparison</title>
<style>
  :root {{
    --bg: #f4f6f9;
    --card: #ffffff;
    --header: #1a2744;
    --text: #1e2532;
    --muted: #6b7280;
    --border: #e2e8f0;
    --best-bg: #d1fae5;
    --best-text: #065f46;
    --best-border: #6ee7b7;
    --radius: 12px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); min-height: 100vh; }}

  /* ── Header ── */
  header {{
    background: var(--header);
    color: #fff;
    padding: 24px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 12px rgba(0,0,0,.25);
  }}
  header .brand {{ display: flex; align-items: center; gap: 12px; }}
  header .brand svg {{ width: 36px; height: 36px; fill: #60a5fa; }}
  header h1 {{ font-size: 1.5rem; font-weight: 700; letter-spacing: -.5px; }}
  header .subtitle {{ font-size: .85rem; color: #93c5fd; margin-top: 2px; }}
  .ts-badge {{
    background: rgba(255,255,255,.12);
    border: 1px solid rgba(255,255,255,.2);
    border-radius: 20px;
    padding: 6px 14px;
    font-size: .78rem;
    color: #bfdbfe;
    white-space: nowrap;
  }}

  /* ── Main ── */
  main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px; }}

  /* ── Legend ── */
  .legend {{
    display: flex; flex-wrap: wrap; gap: 10px;
    margin-bottom: 28px;
  }}
  .store-badge {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 12px; border-radius: 20px;
    font-size: .8rem; font-weight: 600;
    border: 2px solid currentColor;
  }}
  .store-dot {{ width: 8px; height: 8px; border-radius: 50%; background: currentColor; }}

  /* ── Item card ── */
  .item-card {{
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: 0 1px 6px rgba(0,0,0,.08);
    margin-bottom: 28px;
    overflow: hidden;
  }}
  .item-header {{
    padding: 18px 24px;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: baseline; gap: 12px;
  }}
  .item-header h2 {{ font-size: 1.15rem; font-weight: 700; }}
  .item-note {{ font-size: .82rem; color: var(--muted); }}

  /* ── Table ── */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
  th {{
    text-align: left; padding: 10px 16px;
    background: #f8fafc; color: var(--muted);
    font-size: .75rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: .05em;
    border-bottom: 2px solid var(--border);
  }}
  td {{ padding: 12px 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f8fafc; }}

  /* Best row */
  tr.best td {{
    background: var(--best-bg) !important;
    color: var(--best-text);
    font-weight: 600;
  }}
  tr.best td:first-child {{ border-left: 4px solid var(--best-border); padding-left: 12px; }}

  /* Unavailable row */
  tr.unavailable td {{ color: #9ca3af; font-style: italic; }}

  /* Hidden rows (collapsed) */
  tr.extra {{ display: none; }}
  tr.extra.visible {{ display: table-row; }}

  .store-pill {{
    display: inline-block;
    padding: 3px 10px; border-radius: 12px;
    font-size: .78rem; font-weight: 700;
    color: #fff;
    white-space: nowrap;
  }}
  .price-big {{ font-size: 1.05rem; font-weight: 700; }}
  .ppo {{ font-size: .82rem; }}
  .size-dim {{ font-size: .8rem; color: var(--muted); }}

  .link-btn {{
    display: inline-block;
    padding: 4px 10px; border-radius: 8px;
    font-size: .78rem; font-weight: 600;
    text-decoration: none;
    background: #eff6ff; color: #1d4ed8;
    border: 1px solid #bfdbfe;
    transition: background .15s;
  }}
  .link-btn:hover {{ background: #dbeafe; }}
  .search-link {{
    background: #f3f4f6; color: #6b7280;
    border-color: #d1d5db;
  }}
  .search-link:hover {{ background: #e5e7eb; }}

  .best-label {{
    display: inline-block;
    background: #059669; color: #fff;
    font-size: .7rem; font-weight: 700;
    padding: 2px 7px; border-radius: 8px;
    margin-left: 6px; vertical-align: middle;
    text-transform: uppercase; letter-spacing: .04em;
  }}

  /* ── Basket summary ── */
  .basket-card {{
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: 0 1px 6px rgba(0,0,0,.08);
    margin-bottom: 28px;
    overflow: hidden;
    border: 2px solid #e0e7ff;
  }}
  .basket-header {{
    padding: 18px 24px;
    border-bottom: 1px solid var(--border);
    background: #f0f4ff;
    display: flex; align-items: baseline; gap: 12px;
  }}
  .basket-header h2 {{ font-size: 1.15rem; font-weight: 700; color: #1e3a8a; }}
  .basket-header .basket-note {{ font-size: .82rem; color: #6b7280; }}
  tr.basket-winner td {{
    background: var(--best-bg) !important;
    color: var(--best-text);
    font-weight: 600;
  }}
  tr.basket-winner td:first-child {{ border-left: 4px solid var(--best-border); padding-left: 12px; }}
  tr.basket-theory td {{
    background: #eff6ff !important;
    color: #1e40af;
    font-style: italic;
  }}
  tr.basket-theory td:first-child {{ border-left: 4px solid #93c5fd; padding-left: 12px; }}
  .incomplete-note {{ font-size: .75rem; color: #9ca3af; margin-top: 2px; }}
  .coverage-pill {{
    display: inline-block;
    font-size: .72rem; font-weight: 600;
    padding: 2px 7px; border-radius: 8px;
    margin-left: 6px;
  }}
  .coverage-full {{ background: #d1fae5; color: #065f46; }}
  .coverage-partial {{ background: #fef3c7; color: #92400e; }}

  /* ── Expand toggle row ── */
  .expand-row td {{
    padding: 8px 16px;
    border-bottom: none;
    background: #f8fafc;
  }}
  .expand-btn {{
    background: none; border: none;
    color: #4b6cb7; font-size: .8rem; font-weight: 600;
    cursor: pointer; padding: 2px 0;
    display: flex; align-items: center; gap: 5px;
  }}
  .expand-btn:hover {{ color: #1d4ed8; }}
  .expand-btn .chevron {{ transition: transform .2s; display: inline-block; }}
  .expand-btn.open .chevron {{ transform: rotate(180deg); }}

  /* ── Footer ── */
  footer {{
    text-align: center; padding: 32px 16px;
    font-size: .78rem; color: var(--muted);
  }}
  footer strong {{ color: #4b5563; }}

  /* ── Refresh box ── */
  .refresh-box {{
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-radius: var(--radius);
    padding: 14px 20px;
    margin-bottom: 28px;
    font-size: .85rem;
    color: #92400e;
  }}
  .refresh-box code {{
    background: #fef3c7; padding: 2px 6px;
    border-radius: 4px; font-family: monospace;
  }}
</style>
</head>
<body>

<header>
  <div class="brand">
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 2a1 1 0 0 0-1 1v1H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h16a2 2 0 0 0
               2-2V6a2 2 0 0 0-2-2h-1V3a1 1 0 1 0-2 0v1H7V3a1 1 0 0 0-1-1zm-2
               5h16v12H4V7zm2 3v2h2v-2H6zm4 0v2h2v-2h-2zm4 0v2h2v-2h-2zM6
               14v2h2v-2H6zm4 0v2h2v-2h-2z"/>
    </svg>
    <div>
      <h1>Shop Crawl</h1>
      <div class="subtitle">Grocery Price Comparison — MN Stores</div>
    </div>
  </div>
  <div class="ts-badge" id="ts-badge">Loading…</div>
</header>

<main>
  <div class="refresh-box">
    💡 <strong>To refresh prices:</strong> run <code>python3 crawler.py</code>
    in the <em>Shop Crawl</em> folder, then reload this page.
  </div>

  <div class="legend" id="legend"></div>
  <div id="basket"></div>
  <div id="cards"></div>
</main>

<footer>
  Prices fetched automatically from public store websites.
  Always verify price at checkout. &nbsp;|&nbsp;
  <strong>Shop Crawl</strong> — built with Claude
</footer>

<script>
const STORES   = {stores_js};
const ITEMS    = {items_js};
const RESULTS  = {results_js};
const TS       = {ts_js};

const STORE_MAP = Object.fromEntries(STORES.map(s => [s.id, s]));
const TOP_N = 3;

// ── Timestamp ──────────────────────────────────────────────────────────────
document.getElementById('ts-badge').textContent =
  'Updated: ' + new Date(TS).toLocaleString('en-US', {{
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit'
  }});

// ── Legend ─────────────────────────────────────────────────────────────────
const legend = document.getElementById('legend');
STORES.forEach(s => {{
  legend.innerHTML += `
    <span class="store-badge" style="color:${{s.color}}">
      <span class="store-dot" style="background:${{s.color}}"></span>
      ${{s.name}}
    </span>`;
}});

// ── Cards ──────────────────────────────────────────────────────────────────
const container = document.getElementById('cards');

function buildRow(e, isBest, isExtra, item) {{
  const s = e.store;
  const r = e.result;
  const extraClass = isExtra ? 'extra' : '';
  const bestClass  = isBest  ? 'best'  : '';

  if (!r || r.error || !r.price) {{
    const searchUrl = (r && r.search_url) ? r.search_url : '#';
    return `<tr class="unavailable ${{extraClass}}">
      <td><span class="store-pill" style="background:${{s.color}}">${{s.name}}</span></td>
      <td colspan="3">Not available / couldn't retrieve</td>
      <td><a class="link-btn search-link" href="${{searchUrl}}" target="_blank">Search →</a></td>
    </tr>`;
  }}

  const priceStr  = '$' + r.price.toFixed(2);
  const ppoStr    = r.price_per_oz
    ? ('$' + r.price_per_oz.toFixed(4) + ' /' + item.unit_label)
    : '—';
  const sizeStr   = r.size_oz ? (r.size_oz % 1 === 0 ? r.size_oz.toFixed(0) : r.size_oz.toFixed(2)) + ' ' + item.unit_label : '—';
  const bestBadge = isBest ? '<span class="best-label">Best</span>' : '';

  return `<tr class="${{bestClass}} ${{extraClass}}">
    <td><span class="store-pill" style="background:${{s.color}}">${{s.name}}</span></td>
    <td>${{r.name}}${{bestBadge}}</td>
    <td class="price-big">${{priceStr}}</td>
    <td class="size-dim">${{sizeStr}}</td>
    <td class="ppo">${{ppoStr}}</td>
    <td><a class="link-btn" href="${{r.url}}" target="_blank">View →</a></td>
  </tr>`;
}}

// ── Basket Summary ─────────────────────────────────────────────────────────
(function() {{
  const basketEl = document.getElementById('basket');
  const totalItems = ITEMS.length;
  const BASKET_TOP_N = 3;
  const basketCardId = 'basket-summary-card';

  // Per-store totals
  const storeBaskets = STORES.map(store => {{
    let total = 0, covered = 0;
    const missing = [];
    ITEMS.forEach(item => {{
      const r = (RESULTS[item.id] || {{}})[store.id];
      if (r && !r.error && r.price) {{ total += r.price; covered++; }}
      else missing.push(item.name);
    }});
    return {{ store, total, covered, missing, complete: covered === totalItems }};
  }});

  // Sort: complete baskets first (by total asc), then partial (by covered desc, total asc)
  const sorted = [...storeBaskets].sort((a, b) => {{
    if (a.complete !== b.complete) return a.complete ? -1 : 1;
    if (a.covered !== b.covered) return b.covered - a.covered;
    return a.total - b.total;
  }});

  // Theoretical minimum: best price per item across all stores
  let theoryTotal = 0; let theoryComplete = true;
  const theoryLines = ITEMS.map(item => {{
    let bestPrice = Infinity, bestStore = '';
    STORES.forEach(store => {{
      const r = (RESULTS[item.id] || {{}})[store.id];
      if (r && !r.error && r.price && r.price < bestPrice) {{
        bestPrice = r.price; bestStore = store.name;
      }}
    }});
    if (bestPrice === Infinity) {{ theoryComplete = false; return null; }}
    theoryTotal += bestPrice;
    return `${{item.name}} @ ${{bestStore}} ($${{bestPrice.toFixed(2)}})`;
  }}).filter(Boolean);

  const winnerIdx = sorted.findIndex(b => b.complete);
  const theoryTip = theoryLines.join(' · ');

  function buildBasketRow(b, idx, isExtra) {{
    const isWinner = idx === winnerIdx;
    const coveragePill = b.complete
      ? `<span class="coverage-pill coverage-full">${{totalItems}}/${{totalItems}} items</span>`
      : `<span class="coverage-pill coverage-partial">${{b.covered}}/${{totalItems}} items</span>`;
    const missingNote = b.missing.length
      ? `<div class="incomplete-note">Missing: ${{b.missing.join(', ')}}</div>` : '';
    const rowClass = [isWinner ? 'basket-winner' : '', isExtra ? 'extra' : ''].filter(Boolean).join(' ');
    const winBadge = isWinner ? '<span class="best-label">Best</span>' : '';
    return `<tr class="${{rowClass}}">
      <td><span class="store-pill" style="background:${{b.store.color}}">${{b.store.name}}</span></td>
      <td>${{coveragePill}}${{missingNote}}</td>
      <td class="price-big">$${{b.total.toFixed(2)}}${{winBadge}}</td>
    </tr>`;
  }}

  const topRows  = sorted.slice(0, BASKET_TOP_N);
  const restRows = sorted.slice(BASKET_TOP_N);
  const hasMore  = restRows.length > 0;

  // Theory row pinned at top
  const theoryRow = `<tr class="basket-theory" title="${{theoryTip}}">
    <td><em>Best possible (mix stores)</em></td>
    <td><span class="coverage-pill coverage-${{theoryComplete ? 'full' : 'partial'}}">${{theoryComplete ? totalItems : '?'}}/${{totalItems}} items</span></td>
    <td class="price-big">$${{theoryTotal.toFixed(2)}}</td>
  </tr>`;

  let rows = theoryRow;
  rows += topRows.map((b, i) => buildBasketRow(b, i, false)).join('');

  const expandRow = hasMore ? `
    <tr class="expand-row">
      <td colspan="3">
        <button class="expand-btn" onclick="toggleExpand('${{basketCardId}}', this)">
          <span class="chevron">▼</span>
          <span class="label">Show ${{restRows.length}} more store${{restRows.length > 1 ? 's' : ''}}</span>
        </button>
      </td>
    </tr>` : '';

  rows += expandRow;
  rows += restRows.map((b, i) => buildBasketRow(b, i + BASKET_TOP_N, true)).join('');

  basketEl.innerHTML = `
    <div class="basket-card" id="${{basketCardId}}">
      <div class="basket-header">
        <h2>🛒 Full Basket Total</h2>
        <span class="basket-note">One of everything — ranked cheapest to most expensive</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Store</th><th>Coverage</th><th>Total</th></tr></thead>
          <tbody>${{rows}}</tbody>
        </table>
      </div>
    </div>`;
}})();

ITEMS.forEach(item => {{
  const itemData = RESULTS[item.id] || {{}};

  const entries = STORES.map(store => {{
    const r = itemData[store.id];
    return {{ store, result: r }};
  }});

  const available   = entries.filter(e => e.result && !e.result.error && e.result.price);
  const unavailable = entries.filter(e => !e.result || e.result.error || !e.result.price);

  available.sort((a, b) => {{
    const va = a.result.price_per_oz ?? a.result.price;
    const vb = b.result.price_per_oz ?? b.result.price;
    return va - vb;
  }});

  const sorted = [...available, ...unavailable];
  const topEntries  = sorted.slice(0, TOP_N);
  const restEntries = sorted.slice(TOP_N);
  const hasMore     = restEntries.length > 0;
  const cardId      = 'card-' + item.id;

  let rows = topEntries.map((e, i) => buildRow(e, i === 0, false, item)).join('');
  rows    += restEntries.map(e => buildRow(e, false, true, item)).join('');

  const expandRow = hasMore ? `
    <tr class="expand-row">
      <td colspan="6">
        <button class="expand-btn" onclick="toggleExpand('${{cardId}}', this)">
          <span class="chevron">▼</span>
          <span class="label">Show ${{restEntries.length}} more store${{restEntries.length > 1 ? 's' : ''}}</span>
        </button>
      </td>
    </tr>` : '';

  container.innerHTML += `
    <div class="item-card" id="${{cardId}}">
      <div class="item-header">
        <h2>${{item.name}}</h2>
        <span class="item-note">${{item.note}}</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Store</th><th>Product</th><th>Price</th>
              <th>Size</th><th>$/Unit</th><th>Link</th>
            </tr>
          </thead>
          <tbody>${{rows}}${{expandRow}}</tbody>
        </table>
      </div>
    </div>`;
}});

function toggleExpand(cardId, btn) {{
  const card = document.getElementById(cardId);
  const extras = card.querySelectorAll('tr.extra');
  const isOpen = btn.classList.contains('open');
  extras.forEach(r => r.classList.toggle('visible', !isOpen));
  btn.classList.toggle('open', !isOpen);
  const count = extras.length;
  btn.querySelector('.label').textContent = isOpen
    ? `Show ${{count}} more store${{count > 1 ? 's' : ''}}`
    : `Hide ${{count}} store${{count > 1 ? 's' : ''}}`;
}}
</script>
</body>
</html>
"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Shop Crawl — Grocery Price Comparison")
    print("=" * 55)

    all_data  = {}
    timestamp = datetime.now().isoformat()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",   # uses your installed Chrome, not Chromium
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/Chicago",
        )
        # Remove telltale webdriver property
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()

        for item in ITEMS:
            print(f"\n📦  {item['name']}")
            item_results = {}

            for store in STORES:
                sid   = store["id"]
                query = item["queries"][sid]
                print(f"    🔍 {store['name']} — searching '{query}'...", end=" ", flush=True)

                scraper    = SCRAPERS.get(sid)
                candidates = scraper(page, query) if scraper else []
                item_filter = item.get("filter", {})
                candidates = [c for c in candidates if passes_filter(c.get("name", ""), item_filter)]
                pick       = best_pick(candidates)

                if pick:
                    ppo_str = f"${pick['price_per_oz']:.4f}/{item['unit_label']}" if pick.get("price_per_oz") else "no size info"
                    print(f"${pick['price']:.2f}  ({ppo_str})")
                    item_results[sid] = pick
                else:
                    print("not found / blocked")
                    item_results[sid] = {
                        "store":      sid,
                        "error":      True,
                        "search_url": search_url_for(sid, query),
                    }

                time.sleep(1.0)   # be polite

            all_data[item["id"]] = item_results

        browser.close()

    # Write dashboard
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    html = generate_dashboard(all_data, timestamp)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅  Dashboard written to:\n    {out_path}\n")
    print("Open dashboard.html in your browser to see prices.")
    print("Re-run crawler.py any time to refresh.\n")


if __name__ == "__main__":
    main()
