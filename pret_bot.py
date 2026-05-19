import cloudscraper
from bs4 import BeautifulSoup
import os
import json
import re

PRODUCT_URL = "https://www.pcgarage.ro/notebook-laptop/lenovo/gaming-16-legion-pro-7-16iax10h-wqxga-oled-240hz-g-sync-procesor-intel-core-ultra-9-275hx-36m-cache-up-to-540-ghz-32gb-ddr5-csodimm-1tb-ssd-geforce-rtx-5080-16gb-no-os-eclipse-black-3yr-onsite-premium-care/"

STATE_FILE = "price_state.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/",
}


def get_price():
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "mobile": False,
        }
    )

    response = scraper.get(
        PRODUCT_URL,
        headers=HEADERS,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"Request failed: {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")

    price_element = soup.select_one(".product-price")

    if price_element:
        price_text = price_element.get_text(strip=True)
    else:
        text = soup.get_text(" ", strip=True)

        matches = re.findall(
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*Lei',
            text
        )

        if not matches:
            raise Exception("Pretul nu a fost gasit")

        price_text = matches[0]

    normalized_price = (
        price_text
        .replace(".", "")
        .replace(",", ".")
    )

    price = float(
        re.findall(r"\d+\.?\d*", normalized_price)[0]
    )

    return price


def load_last_price():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r") as f:
        data = json.load(f)

    return data.get("price")


def save_price(price):
    with open(STATE_FILE, "w") as f:
        json.dump({"price": price}, f)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    response = cloudscraper.create_scraper().post(
        url,
        data=payload,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(
            f"Telegram error: {response.text}"
        )


def main():
    print("Verificare pret Lenovo Legion Pro 7...")

    current_price = get_price()

    print(f"Pret curent: {current_price} Lei")

    last_price = load_last_price()

    if last_price is None:
        save_price(current_price)

        send_telegram(
            f"📦 Tracking pornit\n\n"
            f"Pret initial: {current_price} Lei\n\n"
            f"{PRODUCT_URL}"
        )

        print("Prima rulare completata.")
        return

    if current_price != last_price:
        difference = current_price - last_price

        trend = "📈 Pret crescut"

        if difference < 0:
            trend = "📉 Pret scazut"

        message = (
            f"{trend}\n\n"
            f"Vechi: {last_price} Lei\n"
            f"Nou: {current_price} Lei\n"
            f"Diferenta: {difference:.2f} Lei\n\n"
            f"{PRODUCT_URL}"
        )

        send_telegram(message)

        save_price(current_price)

        print("Pret modificat. Notificare trimisa.")
    else:
        print("Pret neschimbat.")


if __name__ == "__main__":
    main()
