#!/usr/bin/env python3
"""
fetch_ice.py — Pobiera ICE Low Sulphur Gasoil (LF.F) i USD/PLN ze stooq.pl.
Przelicza cenę na PLN/1000l i dopisuje do archiwum.

Wzór: ICE [USD/tonę] × 0,845 [kg/l] × USD/PLN = ICE [PLN/1000l]
Gęstość kontraktowa ICE Low Sulphur Gasoil: 0,845 kg/l (specyfikacja ICE).
"""
import requests
import json
import os
from datetime import date, timedelta

HISTORY_FILE = "data/ice_history.json"
DENSITY = 0.845  # kg/l


def fetch_stooq(symbol, d1, d2):
    url = f"https://stooq.pl/q/d/l/?s={symbol}&i=d&d1={d1}&d2={d2}"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    if len(lines) < 2:
        raise RuntimeError(f"stooq {symbol}: brak danych w odpowiedzi")
    result = {}
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) >= 5:
            try:
                result[parts[0]] = float(parts[4])  # index 4 = Close (Date,Open,High,Low,Close)
            except ValueError:
                pass
    return result


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
    today = date.today()
    history = load_history()

    if history:
        last_date = date.fromisoformat(history[-1]["date"])
        d1 = (last_date + timedelta(days=1)).strftime("%Y%m%d")
    else:
        # Pierwszy run: pobierz ostatnie 90 dni
        d1 = (today - timedelta(days=90)).strftime("%Y%m%d")

    d2 = today.strftime("%Y%m%d")

    if d1 > d2:
        print("ICE: brak nowych danych do pobrania")
        return

    ice_data = fetch_stooq("lf.f", d1, d2)
    usdpln_data = fetch_stooq("usdpln", d1, d2)

    existing = {e["date"] for e in history}
    added = 0

    for record_date in sorted(ice_data.keys()):
        if record_date in existing:
            continue
        if record_date not in usdpln_data:
            print(f"ICE: brak USD/PLN dla {record_date}, pomijam")
            continue

        ice_usd = ice_data[record_date]
        usdpln = usdpln_data[record_date]
        ice_pln = round(ice_usd * DENSITY * usdpln, 2)

        history.append({
            "date": record_date,
            "ice_usd_tonne": ice_usd,
            "usdpln": usdpln,
            "ice_pln_1000l": ice_pln,
        })
        existing.add(record_date)
        added += 1

    if added > 0:
        history.sort(key=lambda e: e["date"])
        save_history(history)
        print(f"ICE: dodano {added} wpisów (ostatni: {history[-1]['date']})")
    else:
        print("ICE: brak nowych wpisów")


if __name__ == "__main__":
    main()
