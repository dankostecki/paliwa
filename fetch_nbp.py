#!/usr/bin/env python3
"""
fetch_nbp.py — Pobiera stopy procentowe NBP z XML i dopisuje do archiwum.
Wpis jest dodawany tylko gdy data obowiązywania jest nowa (tj. RPP zmieniło stopy).
"""
import requests
import xml.etree.ElementTree as ET
import json
import os

URL = "https://static.nbp.pl/dane/stopy/stopy_procentowe.xml"
HISTORY_FILE = "data/nbp_history.json"

NAME_MAP = {
    "Stopa referencyjna": "ref",
    "Stopa lombardowa": "lombard",
    "Stopa depozytowa": "deposit",
    "Stopa redyskontowa weksli": "rediscount",
    "Stopa dyskontowa weksli": "discount",
}


def fetch_rates():
    resp = requests.get(URL, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    # Szukaj daty obowiązywania - może być na <tabela> lub na root
    date = None
    tabela = root.find("tabela")
    if tabela is not None:
        date = tabela.attrib.get("obowiazuje_od")
    if not date:
        date = root.attrib.get("obowiazuje_od")
    # Fallback: przeszukaj wszystkie elementy
    if not date:
        for elem in root.iter():
            d = elem.attrib.get("obowiazuje_od")
            if d:
                date = d
                break

    rates = {}
    for pozycja in root.iter("pozycja"):
        nazwa = pozycja.attrib.get("nazwa", "")
        key = NAME_MAP.get(nazwa)
        if key:
            raw = pozycja.attrib.get("oprocentowanie", "").replace(",", ".")
            try:
                rates[key] = float(raw)
            except ValueError:
                pass

    print(f"NBP debug: date={date}, rates={rates}")
    return date, rates


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
    date, rates = fetch_rates()

    if not date or not rates:
        print("NBP: brak danych w XML")
        return

    history = load_history()

    # Dodaj tylko jeśli data obowiązywania jest nowa
    if history and history[0].get("date") == date:
        print(f"NBP: brak zmian (data: {date}), pomijam")
        return

    entry = {"date": date, **rates}
    history.append(entry)
    history.sort(key=lambda e: e["date"], reverse=True)
    save_history(history)
    print(f"NBP: dodano wpis dla {date} (ref={rates.get('ref')}%)")


if __name__ == "__main__":
    main()
