from playwright.sync_api import sync_playwright
import json
import os
import re
import requests

PRODUCT_URL = "https://www.pcgarage.ro/notebook-laptop/lenovo/gaming-16-legion-pro-7-16iax10h-wqxga-oled-240hz-g-sync-procesor-intel-core-ultra-9-275hx-36m-cache-up-to-540-ghz-32gb-ddr5-csodimm-1tb-ssd-geforce-rtx-5080-16gb-no-os-eclipse-black-3yr-onsite-premium-care/"

STATE_FILE = "price_state.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def get_price():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ro-RO"
        )

        page.goto(
            PRODUCT_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(5000)

        content = page.content()

        browser.close()

    matches = re.findall(
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*Lei',
        content
    )

    if not matches:
        raise Exception("Pretul nu a fost gasit")

    raw_price = matches[0]

    normalized = raw_price.replace(".", "").replace(",", ".")

    return float(normalized)


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
    }

    response = requests.post(
        url,
        data=payload,
        timeout=30
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

        send_telegram(
            f"{trend}\n\n"
            f"Vechi: {last_price} Lei\n"
            f"Nou: {current_price} Lei\n"
            f"Diferenta: {difference:.2f} Lei\n\n"
            f"{PRODUCT_URL}"
        )

        save_price(current_price)

        print("Pret modificat.")
    else:
        print("Pret neschimbat.")


if __name__ == "__main__":
    main()
