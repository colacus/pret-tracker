import requests
from bs4 import BeautifulSoup
import os
import re
import json

URL = "https://www.pcgarage.ro/notebook-laptop/lenovo/gaming-16-legion-pro-7-16iax10h-wqxga-oled-240hz-g-sync-procesor-intel-core-ultra-9-275hx-36m-cache-up-to-540-ghz-32gb-ddr5-csodimm-1tb-ssd-geforce-rtx-5080-16gb-no-os-eclipse-black-3yr-onsite-premium-care/"
PRICE_FILE = "last_price.json"

# Setează prețul la care vrei să fii anunțat (în Lei)
# Dacă prețul SCADE sub această valoare, primești notificare
TARGET_PRICE = 14000

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8",
}


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    print("Notificare Telegram trimisă.")


def extract_price_from_js(html):
    """
    Extrage prețul din linia JS: setEcommerceView(..., 14875.1983)
    Aceasta este metoda principală pe PCGarage.
    """
    match = re.search(r"setEcommerceView.*?(\d+\.\d+)", html)
    if match:
        return int(float(match.group(1)))
    return None


def extract_price_from_html(soup):
    """
    Fallback: caută în HTML clasic dacă metoda JS eșuează.
    """
    el = soup.select_one('[class*="price"]')
    if el:
        text = el.get_text(strip=True)
        text = re.sub(r"[^\d]", "", text)
        if text:
            return int(text)
    return None


def get_price():
    response = requests.get(URL, headers=HEADERS, timeout=15)
    if response.status_code != 200:
        raise Exception(f"Request failed: {response.status_code}")

    html = response.text

    # Metoda 1: extrage din JS (cea mai fiabilă pe PCGarage)
    price = extract_price_from_js(html)
    if price:
        print(f"Preț extras din JS: {price} Lei")
        return price

    # Metoda 2: fallback HTML
    soup = BeautifulSoup(html, "html.parser")
    price = extract_price_from_html(soup)
    if price:
        print(f"Preț extras din HTML: {price} Lei")
        return price

    # Debug: afișează primele 2000 caractere din HTML pentru diagnosticare
    print("=== DEBUG HTML (primele 2000 caractere) ===")
    print(html[:2000])
    raise Exception("Nu am putut găsi prețul (JS + HTML fail)")


def load_last_price():
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r") as f:
            data = json.load(f)
            return data.get("price")
    return None


def save_price(price):
    with open(PRICE_FILE, "w") as f:
        json.dump({"price": price}, f)


def main():
    print(f"Verificare preț laptop Lenovo Legion Pro 7...")

    current_price = get_price()
    print(f"Preț curent: {current_price} Lei")

    last_price = load_last_price()
    print(f"Ultimul preț salvat: {last_price} Lei")

    # Prima rulare: salvează prețul de referință
    if last_price is None:
        save_price(current_price)
        send_telegram(
            f"🤖 <b>Price Tracker pornit!</b>\n\n"
            f"📦 <b>Lenovo Legion Pro 7 (RTX 5080)</b>\n"
            f"💰 Preț înregistrat: <b>{current_price} Lei</b>\n"
            f"🎯 Alertă activată sub: <b>{TARGET_PRICE} Lei</b>\n\n"
            f"<a href='{URL}'>Vezi produsul</a>"
        )
        print("Prima rulare — preț salvat și confirmare trimisă pe Telegram.")
        return

    # Preț scăzut față de ultima verificare ȘI sub TARGET_PRICE
    if current_price < last_price and current_price <= TARGET_PRICE:
        diff = last_price - current_price
        pct = (diff / last_price) * 100
        send_telegram(
            f"📉 <b>ALERTĂ SCĂDERE DE PREȚ!</b>\n\n"
            f"📦 <b>Lenovo Legion Pro 7 (RTX 5080)</b>\n"
            f"💸 Preț vechi: {last_price} Lei\n"
            f"✅ Preț nou: <b>{current_price} Lei</b>\n"
            f"🎉 Economisești: <b>{diff} Lei ({pct:.1f}%)</b>\n\n"
            f"<a href='{URL}'>🛒 Cumpără acum</a>"
        )
        save_price(current_price)
        print(f"Alertă trimisă! {last_price} → {current_price} Lei")

    # Preț scăzut dar NU sub target — actualizăm referința fără notificare
    elif current_price < last_price:
        save_price(current_price)
        print(f"Preț scăzut ({last_price} → {current_price} Lei) dar încă peste target ({TARGET_PRICE} Lei). Fără alertă.")

    # Preț crescut — actualizăm referința
    elif current_price > last_price:
        save_price(current_price)
        print(f"Preț crescut: {last_price} → {current_price} Lei. Fără notificare.")

    # Preț neschimbat
    else:
        print(f"Prețul nu s-a schimbat: {current_price} Lei.")


if __name__ == "__main__":
    main()
