from playwright.sync_api import sync_playwright
import json
import os
import re
import requests
from urllib.parse import urlparse

PRODUCTS_FILE = "products.json"  # <- lista pe care o editezi tu


def load_products():
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        items = json.load(f)
    for p in items:
        # "id" e optional; implicit e URL-ul fara parametri (?...)
        p.setdefault("id", p["url"].split("?")[0])
        p.setdefault("name", None)
        p.setdefault("target", None)
    return items


STATE_FILE = "price_state.json"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def parse_ro_price(text):
    """'1.699,99 lei' -> 1699.99"""
    match = re.search(r"(\d[\d\.\,]*)", text)
    if not match:
        raise Exception(f"Nu am putut extrage numarul din: {text}")
    return float(match.group(1).replace(".", "").replace(",", "."))


# ---------------- extractori per magazin ----------------

def price_pcgarage(page):
    selectors = [".product-price", ".price", ".ps-price", "[data-price]",
                 ".selling-price", ".product-price-current"]
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0:
                text = el.inner_text().strip()
                if text:
                    print(f"Selector gasit: {selector} -> {text}")
                    return parse_ro_price(text)
        except Exception:
            pass
    raise Exception("Pretul nu a fost gasit (pcgarage)")


def price_generic(page):
    # 1) JSON-LD (cel mai stabil, daca exista)
    for raw in page.locator('script[type="application/ld+json"]').all_inner_texts():
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            offers = item.get("offers") if isinstance(item, dict) else None
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict) and offers.get("price"):
                print(f"Pret din JSON-LD: {offers['price']}")
                return float(str(offers["price"]).replace(",", "."))

    # 2) meta tag
    for sel in ['meta[property="product:price:amount"]',
                'meta[property="og:price:amount"]',
                'meta[itemprop="price"]']:
        el = page.locator(sel).first
        if el.count() > 0:
            val = el.get_attribute("content")
            if val:
                print(f"Pret din {sel}: {val}")
                return float(val.replace(",", "."))

    # 3) fallback: primul "1.699,99 lei" din textul paginii
    body = page.locator("body").inner_text()
    m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*lei", body)
    if m:
        print(f"Pret din text: {m.group(0)}")
        return parse_ro_price(m.group(1))

    raise Exception("Pretul nu a fost gasit (generic)")


def extractor_for(url):
    host = urlparse(url).netloc
    if "pcgarage.ro" in host:
        return price_pcgarage
    return price_generic  # altex.ro si orice alt site


def get_price(product):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = browser.new_page(user_agent=USER_AGENT, locale="ro-RO")
            page.goto(product["url"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            price = extractor_for(product["url"])(page)
            return price, page.title().strip()
        finally:
            browser.close()


# ---------------- stare + telegram ----------------

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        data = json.load(f)
    # compatibilitate cu formatul vechi {"price": 123}
    if "price" in data and not isinstance(data["price"], dict):
        return {"legion-pro-7": data["price"]}
    return data


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_telegram(message):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": message},
        timeout=30,
    )
    if r.status_code != 200:
        raise Exception(f"Telegram error: {r.text}")


def check_product(product, state):
    pid, url = product["id"], product["url"]
    print(f"\nVerificare {product['name'] or url}...")

    current, title = get_price(product)
    name = product["name"] or title
    last = state.get(pid)
    print(f"Pret curent: {current} Lei (anterior: {last})")

    if last is None:
        send_telegram(f"📦 Tracking pornit: {name}\n\nPret initial: {current} Lei\n\n{url}")
    elif current != last:
        diff = current - last
        trend = "📉 Pret scazut" if diff < 0 else "📈 Pret crescut"
        msg = (f"{trend}: {name}\n\nVechi: {last} Lei\nNou: {current} Lei\n"
               f"Diferenta: {diff:.2f} Lei\n\n{url}")
        target = product.get("target")
        if target is not None and current <= target:
            msg = f"🎯 SUB PRAGUL DE {target} Lei!\n\n" + msg
        send_telegram(msg)
    else:
        print("Pret neschimbat.")

    state[pid] = current


def main():
    state = load_state()
    failed = False

    for product in load_products():
        try:
            check_product(product, state)
        except Exception as e:
            # un produs picat nu le opreste pe celelalte
            print(f"EROARE la {product['name'] or product['url']}: {e}")
            failed = True
        save_state(state)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
