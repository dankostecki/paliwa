#!/usr/bin/env python3
"""
orlen_scraper.py — Scraper hurtowych cen paliw Orlen
=====================================================
Pobiera PB95 i Ekodiesel z orlen.pl (Playwright)
lub cenypaliw.fyi (fallback) i dopisuje do JSON + CSV.

Zoptymalizowany pod GitHub Actions (patrz .github/workflows/scrape.yml)
"""

import os
import sys
import csv
import json
import re
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

# ===== KONFIGURACJA =====
DATA_DIR = Path(__file__).parent

JSON_FILES = {
    "pb95":   DATA_DIR / "Benzyna_Eurosuper95_2022-2026.json",
    "diesel": DATA_DIR / "Olej_Napedowy_Ekodiesel_2022-2026.json",
}
CSV_FILES = {
    "pb95":   DATA_DIR / "Benzyna_Eurosuper95_2022-2026.csv",
    "diesel": DATA_DIR / "Olej_Napedowy_Ekodiesel_2022-2026.csv",
}

ORLEN_URL = "https://www.orlen.pl/pl/dla-biznesu/hurtowe-ceny-paliw"
WARSAW = ZoneInfo("Europe/Warsaw")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("orlen_scraper")


# ===== PLAYWRIGHT (primary) =====

def scrape_orlen_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright nie zainstalowany")
        return None

    log.info("Playwright -> orlen.pl ...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(ORLEN_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(8000)
            text = page.inner_text("body")
            browser.close()

        return parse_orlen_text(text)
    except Exception as e:
        log.error(f"Playwright error: {e}")
        return None


def parse_orlen_text(text):
    text = re.sub(r'[\t ]+', ' ', text)
    prices = {}

    pb95 = re.search(
        r'(?:Eurosuper\s*95|Benzyna\s*bezołowiowa\s*-?\s*Eurosuper\s*95)\s*[\s\S]{0,100}?(\d[\s\d]*\d{3})',
        text, re.IGNORECASE
    )
    if pb95:
        prices["pb95"] = int(pb95.group(1).replace(" ", "").replace("\u00a0", ""))

    diesel = re.search(
        r'(?:Olej\s*Nap(?:ę|e)dowy\s*Ekodiesel|Ekodiesel)\s*[\s\S]{0,100}?(\d[\s\d]*\d{3})',
        text, re.IGNORECASE
    )
    if diesel:
        prices["diesel"] = int(diesel.group(1).replace(" ", "").replace("\u00a0", ""))

    if prices:
        log.info(f"Playwright OK: {prices}")
    return prices if prices else None


# ===== FALLBACK (cenypaliw.fyi) =====

def scrape_fallback():
    import requests

    log.info("Fallback -> cenypaliw.fyi ...")

    try:
        resp = requests.get("https://cenypaliw.fyi/", timeout=15,
                            headers={"User-Agent": "OrlenScraper/1.0"})
        resp.raise_for_status()
        text = resp.text
        prices = {}

        pb = re.search(r'PB\s*95.*?(\d+\.\d+)\s*PLN/l', text, re.IGNORECASE | re.DOTALL)
        if pb:
            prices["pb95"] = int(round(float(pb.group(1)) * 1000))

        on = re.search(r'(?<!\w)ON(?!\s*Ekoterm).*?(\d+\.\d+)\s*PLN/l', text, re.IGNORECASE | re.DOTALL)
        if on:
            prices["diesel"] = int(round(float(on.group(1)) * 1000))

        if prices:
            log.info(f"Fallback OK: {prices}")
        return prices if prices else None
    except Exception as e:
        log.error(f"Fallback error: {e}")
        return None


# ===== JSON =====

def load_json(filepath):
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_json(filepath, date_str, price):
    data = load_json(filepath)

    # JSON jest posortowany DESC (najnowsza data pierwsza)
    # Szybkie sprawdzenie: jesli najnowszy wpis ma ta sama date — pomijamy
    if data and data[0].get("data_zmiany") == date_str:
        log.info(f"JSON: {date_str} juz istnieje w {filepath.name}")
        return False

    # Dla pewnosci sprawdz tez glebiej (na wypadek blednej kolejnosci)
    for entry in data:
        if entry.get("data_zmiany") == date_str:
            log.info(f"JSON: {date_str} juz istnieje w {filepath.name}")
            return False

    # Wstaw na poczatek (zachowaj kolejnosc DESC)
    data.insert(0, {"data_zmiany": date_str, "cena_pln_m3": price})
    save_json(filepath, data)
    log.info(f"JSON: +{date_str} -> {price} w {filepath.name}")
    return True


# ===== CSV =====

def append_csv(filepath, date_str, price):
    # Sprawdz duplikat
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("data_zmiany") or "").strip() == date_str:
                    log.info(f"CSV: {date_str} juz istnieje w {filepath.name}")
                    return False

    file_exists = filepath.exists()
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["data_zmiany", "cena_pln_m3"])
        writer.writerow([date_str, price])

    log.info(f"CSV: +{date_str} -> {price} w {filepath.name}")
    return True


# ===== MAIN =====

def main():
    log.info("=" * 50)
    log.info("START — scraper cen paliw Orlen")

    date_str = datetime.now(WARSAW).strftime("%d-%m-%Y")
    log.info(f"Data: {date_str}")

    prices = scrape_orlen_playwright()
    if not prices:
        prices = scrape_fallback()
    if not prices:
        log.error("Nie udalo sie pobrac danych!")
        sys.exit(1)

    updated = 0
    for key in ["pb95", "diesel"]:
        if key not in prices:
            log.warning(f"Brak ceny {key}")
            continue

        price = prices[key]
        if not (2000 <= price <= 15000):
            log.warning(f"Cena {key}={price} poza zakresem, pomijam")
            continue

        if append_json(JSON_FILES[key], date_str, price):
            updated += 1
        append_csv(CSV_FILES[key], date_str, price)

    log.info(f"KONIEC — zaktualizowano {updated} plikow")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
