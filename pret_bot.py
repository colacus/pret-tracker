import requests
from bs4 import BeautifulSoup
import os

URL = "https://www.pcgarage.ro/notebook-laptop/lenovo/gaming-16-legion-pro-7-16iax10h-wqxga-oled-240hz-g-sync-procesor-intel-core-ultra-9-275hx-36m-cache-up-to-540-ghz-32gb-ddr5-csodimm-1tb-ssd-geforce-rtx-5080-16gb-no-os-eclipse-black-3yr-onsite-premium-care/"

TARGET_PRICE = 14000  # pragul tău

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

headers = {
    "User-Agent": "Mozilla/5.0"
}

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": msg}
    requests.get(url, params=params)

def get_price():
    page = requests.get(URL, headers=headers)
    soup = BeautifulSoup(page.text, "html.parser")

    price_text = soup.select_one(".price").get_text(strip=True)
    price = int(price_text.replace(".", "").replace("Lei", "").strip())
    return price

def main():
    price = get_price()
    print("Preț curent:", price)

    if price <= TARGET_PRICE:
        send_telegram(f"🔥 Reducere! Laptopul este acum {price} Lei\n{URL}")

if __name__ == "__main__":
    main()
