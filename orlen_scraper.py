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


# Dokladnie 4-5 cyfr, z opcjonalna spacja tysiecy ("6 410" albo "6410").
# Poprzednie \d[\s\d]*\d{3} lapalo dowolnie dlugi ciag cyfr i spacji.
PRICE_RE = r'(\d{1,2}[\s ]?\d{3})'

# Odstep miedzy nazwa paliwa a cena. Bylo 100 znakow — tak szeroka luka
# pozwalala obu wzorcom trafic w to samo pole, gdy layout strony sie przesunal
# (stad identyczne pb95 == diesel w archiwum: 21-04, 26-04 i 30-06-2026).
GAP = r'[\s\S]{0,40}?'


def parse_orlen_text(text):
    text = re.sub(r'[\t ]+', ' ', text)
    prices = {}

    pb95 = re.search(
        r'(?:Eurosuper\s*95|Benzyna\s*bezołowiowa\s*-?\s*Eurosuper\s*95)\s*' + GAP + PRICE_RE,
        text, re.IGNORECASE
    )
    if pb95:
        prices["pb95"] = int(pb95.group(1).replace(" ", "").replace("\u00a0", ""))

    diesel = re.search(
        r'(?:Olej\s*Nap(?:ę|e)dowy\s*Ekodiesel|Ekodiesel)\s*' + GAP + PRICE_RE,
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


# ===== WALIDACJA =====

# Cala historia 2022-2026 miesci sie w 4470-7704 PLN/m3.
PRICE_MIN = 3000
PRICE_MAX = 9000

# Najwiekszy prawdziwy ruch dzien-do-dnia w historii to -12,15% (31-12-2022,
# zmiana VAT na paliwa). Najmniejszy znany artefakt parsera to +15,07%.
# 15% to jedyny prog, ktory oddziela jedno od drugiego bez falszywych alarmow —
# sprawdzone na calym archiwum 2022-2026.
MAX_DAILY_MOVE_PCT = 15.0


def last_price(filepath):
    """Ostatnia zapisana cena z archiwum (JSON posortowany DESC) lub None."""
    data = load_json(filepath)
    return data[0].get("cena_pln_m3") if data else None


def validate_prices(prices):
    """Sprawdza komplet cen przed zapisem. Zwraca liste bledow (pusta = OK)."""
    errors = []
    pb95 = prices.get("pb95")
    diesel = prices.get("diesel")

    # Oba archiwa maja identyczna liczbe wpisow przez cale 2022-2026 — ceny
    # zawsze przychodza para. Brak jednej oznacza, ze layout strony sie zmienil
    # i druga tez jest podejrzana, wiec nie zapisujemy niczego.
    for key in ("pb95", "diesel"):
        if prices.get(key) is None:
            errors.append(f"brak ceny {key} — parser nie znalazl jej na stronie")

    # Obie ceny identyczne = parser wzial jedna liczbe dla obu paliw.
    # Realny spread to +170..+1538 PLN, nigdy 0.
    if pb95 is not None and diesel is not None and pb95 == diesel:
        errors.append(
            f"pb95 == diesel == {pb95} — parser zwrocil te sama liczbe dla obu paliw"
        )

    for key in ("pb95", "diesel"):
        price = prices.get(key)
        if price is None:
            continue

        if not (PRICE_MIN <= price <= PRICE_MAX):
            errors.append(f"{key}={price} poza zakresem {PRICE_MIN}-{PRICE_MAX} PLN/m3")
            continue

        prev = last_price(JSON_FILES[key])
        if prev:
            move = abs(price - prev) / prev * 100
            if move > MAX_DAILY_MOVE_PCT:
                errors.append(
                    f"{key}: skok {prev} -> {price} ({move:.1f}%) "
                    f"przekracza limit {MAX_DAILY_MOVE_PCT}%"
                )

    return errors


# ===== MAIN =====

def main():
    log.info("=" * 50)
    log.info("START — scraper cen paliw Orlen")

    date_str = datetime.now(WARSAW).strftime("%d-%m-%Y")
    log.info(f"Data: {date_str}")

    # Bierzemy pierwsze zrodlo, ktore da KOMPLET cen. Niekompletny odczyt
    # zwykle znaczy, ze layout strony sie zmienil, wiec warto sprobowac
    # drugiego zrodla zanim sie poddamy.
    prices = None
    for name, scraper in (("orlen.pl", scrape_orlen_playwright),
                          ("cenypaliw.fyi", scrape_fallback)):
        result = scraper()
        if not result:
            continue
        prices = result
        if "pb95" in result and "diesel" in result:
            log.info(f"Komplet cen ze zrodla: {name}")
            break
        log.warning(f"{name}: niekompletne dane ({sorted(result)}), probuje dalej")

    if not prices:
        log.error("Nie udalo sie pobrac danych z zadnego zrodla!")
        sys.exit(1)

    log.info(f"Odczytane ceny: pb95={prices.get('pb95')} diesel={prices.get('diesel')}")

    # Walidacja jest calo-albo-nic: jesli parser pomylil pola, zadna z cen
    # nie jest wiarygodna, wiec nie zapisujemy ani jednej.
    errors = validate_prices(prices)
    if errors:
        for err in errors:
            log.error(f"WALIDACJA: {err}")
        log.error("Odrzucam caly komplet danych — nic nie zapisuje")
        sys.exit(1)

    # Po walidacji obie ceny na pewno sa obecne i sensowne.
    updated = 0
    for key in ["pb95", "diesel"]:
        price = prices[key]
        if append_json(JSON_FILES[key], date_str, price):
            updated += 1
        append_csv(CSV_FILES[key], date_str, price)

    log.info(f"KONIEC — zaktualizowano {updated} plikow")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
