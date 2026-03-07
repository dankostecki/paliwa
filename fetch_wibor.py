#!/usr/bin/env python3
"""
fetch_wibor.py — Pobiera WIBOR 3M ze stooq.pl (CSV) i dopisuje do archiwum.
Jeden wpis dziennie. Pomija jeśli dzisiejsza data już istnieje.
"""
import requests
import json
import os
from datetime import date, timedelta

HISTORY_FILE = "data/wibor_history.json"


import re

def fetch_stooq_json(symbol):
    url = f"https://stooq.pl/q/l/?s={symbol}&f=sd2t2ohlcvn&h=&e=json"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
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

def fetch_wibor():
    # Pobiera z użyciem API JSON dla symbolu plopln3m
    result = fetch_stooq_json("plopln3m")
    if not result:
        raise RuntimeError("stooq: brak danych w odpowiedzi JSON dla WIBOR 3M")
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
    record_date, wibor_3m = fetch_wibor()

    history = load_history()

    if history and history[0].get("date") == record_date:
        print(f"WIBOR: brak zmian (data: {record_date}), pomijam")
        return

    entry = {"date": record_date, "wibor_3m": wibor_3m}
    history.append(entry)
    history.sort(key=lambda e: e["date"], reverse=True)
    save_history(history)
    print(f"WIBOR: dodano wpis dla {record_date} ({wibor_3m}%)")


if __name__ == "__main__":
    main()
