#!/usr/bin/env python3
"""
fetch_ice.py — Pobiera ICE Low Sulphur Gasoil (LF.F) i USD/PLN ze stooq.pl.
Przelicza cenę na PLN/1000l i dopisuje do archiwum.

Pierwsza inicjalizacja: jednorazowy import z Google Sheets CSV.
Codzienne aktualizacje: stooq.pl JSON API (/q/l/).

Wzór: ICE [USD/tonę] × 0,845 [kg/l] × USD/PLN = ICE [PLN/1000l]
Gęstość kontraktowa ICE Low Sulphur Gasoil: 0,845 kg/l (specyfikacja ICE).
"""
import csv
import io
import json
import os
import re
import sys
import requests
from datetime import date

# Windows terminal moze nie obslugiwac UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HISTORY_FILE = "data/ice_history.json"
DENSITY = 0.845  # kg/l

SHEETS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1FRfB6Xctk00eTAyR_8MM3tM1D1UBPYO4F4yZFlhlzMM"
    "/export?format=csv"
)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_stooq_json(symbol):
    """Pobiera bieżące notowanie z API stooq. Zwraca (date_str, close) lub None."""
    url = f"https://stooq.pl/q/l/?s={symbol}&f=sd2t2ohlcvn&h=&e=json"
    resp = requests.get(url, timeout=15, headers=HEADERS)
    resp.raise_for_status()
    # stooq zwraca niepoprawny JSON: "volume":, — naprawia przed parsowaniem
    fixed = re.sub(r'"volume":,', '"volume":null,', resp.text)
    data = json.loads(fixed)
    symbols = data.get("symbols", [])
    if not symbols:
        return None
    s = symbols[0]
    close = s.get("close")
    date_str = s.get("date")
    if not close or not date_str:
        return None
    return date_str, float(close)


def import_from_sheets():
    """Jednorazowy import historii z Google Sheets CSV. Zwraca posortowaną listę wpisów."""
    resp = requests.get(SHEETS_CSV_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    reader = csv.reader(io.StringIO(resp.text))
    rows = list(reader)
    if not rows:
        raise RuntimeError("Google Sheets: pusta odpowiedź")
    entries = []
    for row in rows[1:]:  # pomijaj nagłówek
        if len(row) < 3:
            continue
        try:
            date_str = row[0].strip()
            ice_usd = float(row[1].strip().replace(",", "."))
            usdpln = float(row[2].strip().replace(",", "."))
        except (ValueError, IndexError):
            continue
        ice_pln = round(ice_usd * DENSITY * usdpln, 2)
        entries.append({
            "date": date_str,
            "ice_usd_tonne": ice_usd,
            "usdpln": usdpln,
            "ice_pln_1000l": ice_pln,
        })
    entries.sort(key=lambda e: e["date"])
    return entries


def load_history():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    history = load_history()

    # Jednorazowy import z Google Sheets gdy historia jest pusta
    if not history:
        print("ICE: pusta historia — importuję z Google Sheets...")
        history = import_from_sheets()
        if not history:
            print("ICE: Google Sheets nie zwróciło danych")
            return
        history.sort(key=lambda e: e["date"], reverse=True)
        save_history(history)
        print(f"ICE: zaimportowano {len(history)} wpisów z Google Sheets "
              f"(ostatni: {history[0]['date']})")

    # Pobierz dzisiejsze notowania ze stooq JSON API
    existing = {e["date"] for e in history}

    lf_result = fetch_stooq_json("lf.f")
    if not lf_result:
        print("ICE: stooq nie zwrócił danych dla lf.f, pomijam")
        return
    lf_date, lf_close = lf_result

    if lf_date in existing:
        print(f"ICE: dane dla {lf_date} już istnieją, pomijam")
        return

    usdpln_result = fetch_stooq_json("usdpln")
    if not usdpln_result:
        print("ICE: stooq nie zwrócił danych dla usdpln, pomijam")
        return
    _, usdpln_close = usdpln_result

    ice_pln = round(lf_close * DENSITY * usdpln_close, 2)
    history.append({
        "date": lf_date,
        "ice_usd_tonne": lf_close,
        "usdpln": usdpln_close,
        "ice_pln_1000l": ice_pln,
    })
    history.sort(key=lambda e: e["date"], reverse=True)
    save_history(history)
    print(f"ICE: dodano {lf_date}: {lf_close} USD/t × {usdpln_close} = {ice_pln} PLN/1000l")


if __name__ == "__main__":
    main()
