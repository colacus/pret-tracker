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


def to_float(value):
    """'1699.99' / '1699,99' / '1.699,99' -> float"""
    v = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        v = v.replace(",", ".")
    return float(v)


def find_price_in_json(node):
    """cauta recursiv 'price' / 'lowPrice' intr-un JSON-LD"""
    if isinstance(node, dict):
        for key in ("price", "lowPrice"):
            if node.get(key) not in (None, ""):
                try:
                    return to_float(node[key])
                except ValueError:
                    pass
        for v in node.values():
            r = find_price_in_json(v)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_price_in_json(v)
            if r is not None:
                return r
    return None


# numar + "lei"/"ron": 1.699,99 lei | 1699 Lei | 1 699 lei | 599,90 RON
PRICE_RE = re.compile(
    r"(\d{1,3}(?:[. \u00a0]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:lei|ron)\b",
    re.I,
)


def price_generic(page):
    # 1) JSON-LD
    scripts = page.locator('script[type="application/ld+json"]').all_inner_texts()
    for raw in scripts:
        try:
            r = find_price_in_json(json.loads(raw))
        except Exception:
            continue
        if r is not None:
            print(f"Pret din JSON-LD: {r}")
            return r

    # 2) meta tag-uri
    for sel in ['meta[property="product:price:amount"]',
                'meta[property="og:price:amount"]',
                'meta[itemprop="price"]']:
        el = page.locator(sel).first
        if el.count() > 0:
            val = el.get_attribute("content")
            if val:
                print(f"Pret din {sel}: {val}")
                return to_float(val)

    # 3) text: primul pret "xxx lei" care apare DUPA titlul produsului (h1)
    body = page.locator("body").inner_text()
    h1 = ""
    try:
        h1 = page.locator("h1").first.inner_text().strip()
    except Exception:
        pass
    start = body.find(h1) if h1 else -1
    region = body[start:] if start >= 0 else body
    m = PRICE_RE.search(region)
    if m:
        print(f"Pret din text: {m.group(0)}")
        return to_float(m.group(1))

    # nimic gasit -> afiseaza ce vede botul, ca sa putem repara
    print("--- DEBUG: pretul nu a fost gasit ---")
    print("Titlu pagina:", page.title())
    print("h1:", h1)
    print("Blocuri JSON-LD:", len(scripts))
    print("Lungime text pagina:", len(body))
    for mm in list(PRICE_RE.finditer(body))[:8]:
        ctx = body[max(0, mm.start() - 40): mm.end() + 10].replace("\n", " | ")
        print("  candidat:", ctx)
    print("Inceput text pagina:", body[:600].replace("\n", " | "))
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
                  "--disable-http2",  # evita ERR_HTTP2_PROTOCOL_ERROR (Altex)
                  "--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            ctx = browser.new_context(
                user_agent=USER_AGENT,
                locale="ro-RO",
                viewport={"width": 1366, "height": 768},
                extra_http_headers={"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"},
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = ctx.new_page()

            last_err = None
            for attempt in range(1, 4):
                try:
                    page.goto(product["url"], wait_until="domcontentloaded", timeout=60000)
                    break
                except Exception as e:
                    last_err = e
                    print(f"Incercarea {attempt}/3 esuata: {str(e).splitlines()[0]}")
                    page.wait_for_timeout(3000 * attempt)
            else:
                raise last_err

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
