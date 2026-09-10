#!/usr/bin/env python3
"""
fetch_ice.py — Pobiera ICE Low Sulphur Gasoil i USD/PLN, przelicza na PLN/1000l
i dopisuje do archiwum.

Zrodla (w kolejnosci prob):
  gasoil  — Yahoo Finance (yfinance), zapasowo stooq
  USD/PLN — Yahoo Finance (USDPLN=X), zapasowo oficjalne API NBP

Wzor: ICE [USD/tone] x 0,845 [kg/l] x USD/PLN = ICE [PLN/1000l]
Gestosc kontraktowa ICE Low Sulphur Gasoil: 0,845 kg/l (specyfikacja ICE).

Skrypt uzupelnia CALA luke miedzy ostatnim wpisem a dniem dzisiejszym, a gdy
zadne zrodlo nie odpowiada i archiwum jest przeterminowane — konczy sie bledem
(kod 1). Poprzednia wersja robila w tej sytuacji print + return, wiec workflow
swiecil na zielono przez 3 miesiace nie pobierajac nic.
"""
import csv
import io
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta

import requests

from lib_fetch import (
    nbp_usdpln_series,
    pick_symbol,
    stooq_csv_series,
    stooq_last_json,
    yf_series,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fetch_ice")

HISTORY_FILE = "data/ice_history.json"
DENSITY = 0.845  # kg/l

SHEETS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1FRfB6Xctk00eTAyR_8MM3tM1D1UBPYO4F4yZFlhlzMM"
    "/export?format=csv"
)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# Kandydaci na symbol gasoilu w Yahoo. Yahoo nie ma udokumentowanego symbolu
# ciaglego dla ICE Low Sulphur Gasoil, wiec probujemy po kolei — patrz
# pick_symbol() w lib_fetch.py. NIE dopisywac tu HO=F: to NYMEX Heating Oil
# notowany w USD/galon, inna gielda i inny poziom cen.
GASOIL_SYMBOLS = ["LF=F", "QS=F", "7F=F", "G=F", "LGO=F", "GAS=F"]
GASOIL_MIN, GASOIL_MAX = 300.0, 3000.0  # USD/tone — pasmo wiarygodnosci

USDPLN_SYMBOLS = ["USDPLN=X", "PLN=X"]
USDPLN_MIN, USDPLN_MAX = 2.5, 6.0

STOOQ_GASOIL = "lf.f"
STOOQ_USDPLN = "usdpln"

# Po tylu dniach bez nowego wpisu uznajemy archiwum za przeterminowane.
STALE_AFTER_DAYS = 7


# ===== ARCHIWUM =====

def load_history():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def import_from_sheets():
    """Jednorazowy import historii z Google Sheets CSV (gdy archiwum puste)."""
    resp = requests.get(SHEETS_CSV_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    entries = []
    for row in list(csv.reader(io.StringIO(resp.text)))[1:]:
        if len(row) < 3:
            continue
        try:
            date_str = row[0].strip()
            ice_usd = float(row[1].strip().replace(",", "."))
            usdpln = float(row[2].strip().replace(",", "."))
        except (ValueError, IndexError):
            continue
        entries.append({
            "date": date_str,
            "ice_usd_tonne": ice_usd,
            "usdpln": usdpln,
            "ice_pln_1000l": round(ice_usd * DENSITY * usdpln, 2),
        })
    entries.sort(key=lambda e: e["date"])
    return entries


# ===== ZRODLA =====

def get_gasoil(start):
    """Seria gasoilu w USD/tone. Yahoo, zapasowo stooq."""
    log.info("Gasoil — szukam symbolu w Yahoo Finance...")
    sym, series = pick_symbol(GASOIL_SYMBOLS, start, GASOIL_MIN, GASOIL_MAX)
    if series:
        log.info(f"Gasoil: uzywam Yahoo '{sym}' ({len(series)} notowan)")
        return series

    log.warning("Gasoil: Yahoo nie dal danych, probuje stooq...")
    series = stooq_csv_series(STOOQ_GASOIL, start) or stooq_last_json(STOOQ_GASOIL)
    if series:
        log.info(f"Gasoil: uzywam stooq '{STOOQ_GASOIL}' ({len(series)} notowan)")
    return series


def get_usdpln(start):
    """Seria USD/PLN. Yahoo, zapasowo NBP, na koncu stooq."""
    log.info("USD/PLN — szukam symbolu w Yahoo Finance...")
    sym, series = pick_symbol(USDPLN_SYMBOLS, start, USDPLN_MIN, USDPLN_MAX)
    if series:
        log.info(f"USD/PLN: uzywam Yahoo '{sym}' ({len(series)} notowan)")
        return series

    log.warning("USD/PLN: Yahoo nie dal danych, probuje API NBP...")
    series = nbp_usdpln_series(start)
    if series:
        log.info(f"USD/PLN: uzywam NBP ({len(series)} notowan). "
                 f"Uwaga: kurs sredni NBP, nie kurs zamkniecia — roznica ok. 0,1%")
        return series

    log.warning("USD/PLN: NBP nie dal danych, probuje stooq...")
    series = stooq_csv_series(STOOQ_USDPLN, start) or stooq_last_json(STOOQ_USDPLN)
    if series:
        log.info(f"USD/PLN: uzywam stooq ({len(series)} notowan)")
    return series


# ===== MAIN =====

def main():
    log.info("=" * 50)
    log.info("START — ICE Gasoil + USD/PLN")

    history = load_history()

    if not history:
        log.info("Puste archiwum — importuje z Google Sheets...")
        history = import_from_sheets()
        if not history:
            log.error("Google Sheets nie zwrocilo danych")
            sys.exit(1)
        history.sort(key=lambda e: e["date"], reverse=True)
        save_history(history)
        log.info(f"Zaimportowano {len(history)} wpisow (ostatni: {history[0]['date']})")

    existing = {e["date"] for e in history}
    last_date = datetime.strptime(max(existing), "%Y-%m-%d").date()
    start = last_date + timedelta(days=1)
    log.info(f"Ostatni wpis: {last_date}, uzupelniam od {start} do {date.today()}")

    if start > date.today():
        log.info("Archiwum aktualne — nic do zrobienia")
        return

    gasoil = get_gasoil(start)
    usdpln = get_usdpln(start)

    # Laczymy PO DACIE. Poprzednia wersja brala date z ICE i doklejala kurs
    # z dowolnego innego dnia, co cicho mieszalo notowania z roznych sesji.
    added = 0
    for d in sorted(set(gasoil) & set(usdpln)):
        if d in existing:
            continue
        ice_usd, fx = gasoil[d], usdpln[d]
        history.append({
            "date": d,
            "ice_usd_tonne": round(ice_usd, 2),
            "usdpln": round(fx, 5),
            "ice_pln_1000l": round(ice_usd * DENSITY * fx, 2),
        })
        added += 1
        log.info(f"  +{d}: {ice_usd:.2f} USD/t x {fx:.5f} = "
                 f"{round(ice_usd * DENSITY * fx, 2)} PLN/1000l")

    only_gasoil = sorted(set(gasoil) - set(usdpln))
    only_fx = sorted(set(usdpln) - set(gasoil))
    if only_gasoil:
        log.info(f"Pominieto {len(only_gasoil)} dni bez kursu USD/PLN: {only_gasoil[:5]}")
    if only_fx:
        log.info(f"Pominieto {len(only_fx)} dni bez notowania gasoilu: {only_fx[:5]}")

    if added:
        history.sort(key=lambda e: e["date"], reverse=True)
        save_history(history)
        log.info(f"KONIEC — dopisano {added} wpisow (ostatni: {history[0]['date']})")
        return

    # Nic nie dopisano. Jesli archiwum jest swieze, to normalne (weekend,
    # swieto). Jesli stare — zadne zrodlo nie dziala i trzeba o tym glosno
    # powiedziec, zamiast konczyc zielono jak poprzednia wersja.
    age = (date.today() - last_date).days
    if age > STALE_AFTER_DAYS:
        log.error(f"Brak nowych danych, a ostatni wpis ma {age} dni "
                  f"({last_date}). Zadne zrodlo nie odpowiedzialo.")
        sys.exit(1)

    log.info(f"Brak nowych notowan (ostatni wpis sprzed {age} dni) — to normalne")


if __name__ == "__main__":
    main()
