#!/usr/bin/env python3
"""
fetch_wibor.py — Pobiera WIBOR 3M i dopisuje do archiwum.

Zrodlo: stooq (symbol plopln3m). Yahoo Finance nie ma WIBOR-u, a NBP go nie
publikuje (NBP podaje stopy referencyjne, nie fixingi WIBOR), wiec nie ma tu
sensownego zamiennika — zostaje stooq, ale odpytywany przez endpoint CSV,
ktory zwraca cala historie i pozwala uzupelnic luke za jednym razem.
"""
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta

from lib_fetch import stooq_csv_series, stooq_last_json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fetch_wibor")

HISTORY_FILE = "data/wibor_history.json"
SYMBOL = "plopln3m"

# WIBOR 3M w calej historii archiwum miesci sie w okolicach 0,2-8%.
WIBOR_MIN, WIBOR_MAX = 0.0, 15.0

STALE_AFTER_DAYS = 7


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
    log.info("=" * 50)
    log.info("START — WIBOR 3M")

    history = load_history()
    existing = {e["date"] for e in history}

    if existing:
        last_date = datetime.strptime(max(existing), "%Y-%m-%d").date()
        start = last_date + timedelta(days=1)
    else:
        last_date = None
        start = date.today() - timedelta(days=365)
    log.info(f"Ostatni wpis: {last_date}, uzupelniam od {start}")

    series = stooq_csv_series(SYMBOL, start) or stooq_last_json(SYMBOL)
    if not series:
        log.error(f"stooq nie zwrocil danych dla {SYMBOL}")
        sys.exit(1)

    added = 0
    for d in sorted(series):
        if d in existing:
            continue
        value = series[d]
        if not (WIBOR_MIN <= value <= WIBOR_MAX):
            log.warning(f"  {d}: {value}% poza pasmem {WIBOR_MIN}-{WIBOR_MAX}, pomijam")
            continue
        history.append({"date": d, "wibor_3m": value})
        added += 1
        log.info(f"  +{d}: {value}%")

    if added:
        history.sort(key=lambda e: e["date"], reverse=True)
        save_history(history)
        log.info(f"KONIEC — dopisano {added} wpisow (ostatni: {history[0]['date']})")
        return

    age = (date.today() - last_date).days if last_date else 999
    if age > STALE_AFTER_DAYS:
        log.error(f"Brak nowych danych, a ostatni wpis ma {age} dni ({last_date})")
        sys.exit(1)

    log.info(f"Brak nowych notowan (ostatni wpis sprzed {age} dni) — to normalne")


if __name__ == "__main__":
    main()
