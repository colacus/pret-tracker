import requests
from bs4 import BeautifulSoup
import os
import re

URL = "https://www.pcgarage.ro/notebook-laptop/lenovo/gaming-16-legion-pro-7-16iax10h-wqxga-oled-240hz-g-sync-procesor-intel-core-ultra-9-275hx-36m-cache-up-to-540-ghz-32gb-ddr5-csodimm-1tb-ssd-geforce-rtx-5080-16gb-no-os-eclipse-black-3yr-onsite-premium-care/"

TARGET_PRICE = 14000

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

headers = {
    "User-Agent": "Mozilla/5.0"
}

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": msg}
    requests.get(url, params=params)

def extract_price_from_js(html):
    """
    Extrage prețul din:
    setEcommerceView(..., 14875.1983)
    """
    match = re.search(r"setEcommerceView.*?(\d+\.\d+)", html)
    if match:
        return int(float(match.group(1)))
    return None

def extract_price_from_html(soup):
    """
    Fallback dacă apare în HTML clasic
    """
    el = soup.select_one('[class*="price"]')
    if el:
        text = el.get_text(strip=True)
        text = re.sub(r"[^\d]", "", text)
        if text:
            return int(text)
    return None

def get_price():
    response = requests.get(URL, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Request failed: {response.status_code}")

    html = response.text

    # 🔥 1. Încearcă metoda corectă (JS)
    price = extract_price_from_js(html)
    if price:
        return price

    # 🪂 2. Fallback HTML
    soup = BeautifulSoup(html, "html.parser")
    price = extract_price_from_html(soup)
    if price:
        return price

    # 💣 3. Dacă nu găsești nimic → debug real
    print(html[:1000])
    raise Exception("Nu am putut găsi prețul (JS + HTML fail)")

def main():
    price = get_price()
    print("Preț curent:", price)

    if price <= TARGET_PRICE:
        send_telegram(f"🔥 Reducere! Laptopul este acum {price} Lei\n{URL}")

if __name__ == "__main__":
    main()
