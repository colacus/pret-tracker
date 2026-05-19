import requests
from bs4 import BeautifulSoup
import os
import re
import json

URL = "https://www.pcgarage.ro/notebook-laptop/lenovo/gaming-16-legion-pro-7-16iax10h-wqxga-oled-240hz-g-sync-procesor-intel-core-ultra-9-275hx-36m-cache-up-to-540-ghz-32gb-ddr5-csodimm-1tb-ssd-geforce-rtx-5080-16gb-no-os-eclipse-black-3yr-onsite-premium-care/"
PRICE_FILE = "last_price.json"

TARGET_PRICE = 14000

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    print("Notificare Telegram trimisa.")


def extract_price_from_js(html):
    match = re.search(r"setEcommerceView.*?(\d+\.\d+)", html)
    if match:
        return int(float(match.group(1)))
    return None


def extract_price_from_html(soup):
    el = soup.select_one('[class*="price"]')
    if el:
        text = el.get_text(strip=True)
        text = re.sub(r"[^\d]", "", text)
        if text:
            return int(text)
    return None


def get_price():
    session = requests.Session()
    # Viziteaza homepage-ul mai intai ca un browser real (obtine cookies)
    session.get("https://www.pcgarage.ro/", headers=HEADERS, timeout=15)
    # Acum acceseaza pagina produsului cu cookie-urile obtinute
    response = session.get(URL, headers=HEADERS, timeout=15)

    if response.status_code != 200:
        raise Exception(f"Request failed: {response.status_code}")

    html = response.text

    price = extract_price_from_js(html)
    if price:
        print(f"Pret extras din JS: {price} Lei")
        return price

    soup = BeautifulSoup(html, "html.parser")
    price = extract_price_from_html(soup)
    if price:
        print(f"Pret extras din HTML: {price} Lei")
        return price

    print("=== DEBUG HTML (primele 2000 caractere) ===")
    print(html[:2000])
    raise Exception("Nu am putut gasi pretul (JS + HTML fail)")


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
    print("Verificare pret laptop Lenovo Legion Pro 7...")

    current_price = get_price()
    print(f"Pret curent: {current_price} Lei")

    last_price = load_last_price()
    print(f"Ultimul pret salvat: {last_price} Lei")

    if last_price is None:
        save_price(current_price)
        send_telegram(
            f"🤖 <b>Price Tracker pornit!</b>\n\n"
            f"📦 <b>Lenovo Legion Pro 7 (RTX 5080)</b>\n"
            f"💰 Pret inregistrat: <b>{current_price} Lei</b>\n"
            f"🎯 Alerta activata sub: <b>{TARGET_PRICE} Lei</b>\n\n"
            f"<a href='{URL}'>Vezi produsul</a>"
        )
        print("Prima rulare — pret salvat si confirmare trimisa pe Telegram.")
        return

    if current_price < last_price and current_price <= TARGET_PRICE:
        diff = last_price - current_price
        pct = (diff / last_price) * 100
        send_telegram(
            f"📉 <b>ALERTA SCADERE DE PRET!</b>\n\n"
            f"📦 <b>Lenovo Legion Pro 7 (RTX 5080)</b>\n"
            f"💸 Pret vechi: {last_price} Lei\n"
            f"✅ Pret nou: <b>{current_price} Lei</b>\n"
            f"🎉 Economisesti: <b>{diff} Lei ({pct:.1f}%)</b>\n\n"
            f"<a href='{URL}'>🛒 Cumpara acum</a>"
        )
        save_price(current_price)
        print(f"Alerta trimisa! {last_price} -> {current_price} Lei")

    elif current_price < last_price:
        save_price(current_price)
        print(f"Pret scazut ({last_price} -> {current_price} Lei) dar peste target ({TARGET_PRICE} Lei). Fara alerta.")

    elif current_price > last_price:
        save_price(current_price)
        print(f"Pret crescut: {last_price} -> {current_price} Lei.")

    else:
        print(f"Pretul nu s-a schimbat: {current_price} Lei.")


if __name__ == "__main__":
    main()
