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


def fetch_wibor():
    today = date.today()
    d2 = today.strftime("%Y%m%d")
    d1 = (today - timedelta(days=14)).strftime("%Y%m%d")

    url = f"https://stooq.pl/q/d/l/?s=plopln3m&i=d&d1={d1}&d2={d2}"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    lines = resp.text.strip().splitlines()
    if len(lines) < 2:
        raise RuntimeError("stooq: brak danych w odpowiedzi CSV")

    # Ostatnia linia: Data,Otwarcie,Najwyzszy,Najnizszy,Zamkniecie
    last = lines[-1].split(",")
    record_date = last[0]          # np. "2026-03-05"
    close = float(last[-1])        # kolumna Zamkniecie

    return record_date, close


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
