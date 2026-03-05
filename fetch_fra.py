#!/usr/bin/env python3
"""
fetch_fra.py — Pobiera stawki PLN FRA z patria.cz i dopisuje do archiwum.
Uruchamiany 2x dziennie: sesja poranna (~09:00 CET) i popołudniowa (~17:00 CET).
Sesja jest określana na podstawie bieżącej godziny UTC.
"""
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone

HISTORY_FILE = "data/fra_history.json"

URLS = {
    "fra_1x4": "https://www.patria.cz/kurzy/PLN/1x4/fra/graf.html",
    "fra_3x6": "https://www.patria.cz/kurzy/PLN/3x6/fra/graf.html",
    "fra_6x9": "https://www.patria.cz/kurzy/PLN/6x9/fra/graf.html",
    "fra_9x12": "https://www.patria.cz/kurzy/PLN/9x12/fra/graf.html",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def scrape_value(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Szukaj komórki "Aktuální hodnota" i bierz sąsiednią
    for td in soup.find_all("td"):
        if "Aktuální hodnota" in td.get_text():
            sibling = td.find_next_sibling("td")
            if sibling:
                raw = sibling.get_text(strip=True).replace(",", ".")
                return float(raw)

    raise RuntimeError(f"Nie znaleziono 'Aktuální hodnota' na {url}")


def get_session(utc_hour):
    """Sesja poranna jeśli godzina UTC < 13, popołudniowa jeśli >= 13."""
    return "morning" if utc_hour < 13 else "afternoon"


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
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date().isoformat()
    session = get_session(now_utc.hour)
    timestamp = now_utc.isoformat(timespec="seconds")

    history = load_history()

    # Sprawdź czy ta sesja na dziś już istnieje
    for entry in history:
        if entry.get("date") == today and entry.get("session") == session:
            print(f"FRA: sesja '{session}' dla {today} już istnieje, nadpisuję")
            history.remove(entry)
            break

    rates = {}
    for key, url in URLS.items():
        try:
            value = scrape_value(url)
            rates[key] = value
            print(f"FRA {key}: {value}")
        except Exception as e:
            print(f"FRA {key}: blad - {e}")
            rates[key] = None

    entry = {
        "timestamp": timestamp,
        "date": today,
        "session": session,
        **rates,
    }

    history.append(entry)
    # Posortuj po timestamp dla pewności
    history.sort(key=lambda x: x.get("timestamp", ""))
    save_history(history)
    print(f"FRA: dodano wpis {today} sesja={session}")


if __name__ == "__main__":
    main()
