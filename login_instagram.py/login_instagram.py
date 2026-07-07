from playwright.sync_api import sync_playwright
import os

os.makedirs("browser", exist_ok=True)

with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    context = browser.new_context()

    page = context.new_page()

    page.goto("https://www.instagram.com")

    print("="*60)
    print("Silakan login Instagram.")
    print("Kalau sudah masuk HOME Instagram")
    print("Tekan ENTER di terminal.")
    print("="*60)

    input()

    context.storage_state(path="browser/state.json")

    browser.close()

print("Session berhasil disimpan.")