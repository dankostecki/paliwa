#!/usr/bin/env python3
"""
fetch_ice.py — Pobiera ICE Low Sulphur Gasoil i USD/PLN, przelicza na PLN/1000l
i dopisuje do archiwum.

Zrodla (w kolejnosci prob):
  gasoil  — TradingView ICEEUR:ULS1! (historia dzienna) <- PODSTAWOWE,
            zapasowo Yahoo (brak kontraktu), stooq (zapora), scanner TV
  USD/PLN — Yahoo Finance (USDPLN=X) <- dziala, zapasowo API NBP, potem stooq

Wzor: ICE [USD/tone] x 0,845 [kg/l] x USD/PLN = ICE [PLN/1000l]
Gestosc kontraktowa ICE Low Sulphur Gasoil: 0,845 kg/l (specyfikacja ICE).

Skrypt uzupelnia CALA luke miedzy ostatnim wpisem a dniem dzisiejszym, a gdy
zadne zrodlo nie odpowiada i archiwum jest przeterminowane — konczy sie bledem
(kod 1).

Historia awarii: ostatni udany przebieg 2026-06-04, pierwsza porazka
2026-06-05, potem ok. 70 czerwonych przebiegow pod rzad. Poprzednia wersja
przewracala sie niezlapanym wyjatkiem ze stooq (raise_for_status / float("N/D")),
ale miala tez ciche przejscie: gdy stooq zwrocil poprawny JSON z pusta lista
"symbols", robila print + return z kodem 0. Nowy kod lapie wyjatki zrodel i
sprowadza obie sciezki do jednego, jawnego zachowania: albo sa dane, albo
kod 1 z komunikatem.
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
    tradingview_history,
    tradingview_quote,
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

# TradingView — jedyne znalezione dzialajace zrodlo prawdziwego kontraktu.
# Sprawdzone 2026-09-10: Yahoo nie ma gasoilu w ogole (wyszukiwarka symboli
# zwraca same indeksy S&P GSCI), stooq postawil zapore anty-botowa (JS
# proof-of-work), investing.com/Barchart/WSJ zwracaja 403/401, FT i onvista
# maja tylko ETC-y i indeksy. Zadne z nich nie daje serii historycznej,
# dlatego TradingView uzupelnia archiwum tylko o dzien biezacy.
TV_GASOIL_SYMBOL = "ICEEUR:ULS1!"   # dla scannera (fallback, bez historii)
TV_GASOIL_EXCHANGE = "ICEEUR"
TV_GASOIL_TICKER = "ULS1!"
GASOIL_MIN, GASOIL_MAX = 300.0, 3000.0  # USD/tone — pasmo wiarygodnosci

USDPLN_SYMBOLS = ["USDPLN=X", "PLN=X"]
USDPLN_MIN, USDPLN_MAX = 2.5, 6.0

STOOQ_GASOIL = "lf.f"
STOOQ_USDPLN = "usdpln"

# Po tylu dniach bez nowego wpisu uznajemy archiwum za przeterminowane.
STALE_AFTER_DAYS = 7

# Zawsze pobieraj co najmniej tyle dni wstecz, nawet gdy archiwum wyglada na
# aktualne. Bez tego start = max(data)+1, wiec pojedyncza dziura w srodku serii
# nigdy by sie nie zabliznila. Duplikaty i tak odsiewa sprawdzenie `in existing`.
BACKFILL_LOOKBACK_DAYS = 21


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
    """
    Seria gasoilu w USD/tone.

    TradingView jest zrodlem podstawowym, bo jako jedyne faktycznie dziala i bo
    odtwarza dane referencyjne uzytkownika co do grosza. Dla porownania: wpisy,
    ktore w okresie 2026-03-06..2026-06-04 dokladal stooq, rozjezdzaly sie z ta
    seria srednio o 1,73% (max 13,27%), zaden nie byl identyczny.

    Yahoo i stooq zostaja nizej jako zapas, gdyby kiedys wrocily.
    """
    log.info("Gasoil — TradingView (historia dzienna)...")
    series = tradingview_history(TV_GASOIL_TICKER, TV_GASOIL_EXCHANGE, start,
                                 GASOIL_MIN, GASOIL_MAX)
    if series:
        return series

    log.warning("Gasoil: TradingView nie dal historii, probuje Yahoo...")
    sym, series = pick_symbol(GASOIL_SYMBOLS, start, GASOIL_MIN, GASOIL_MAX,
                              currency="USD")
    if series:
        log.info(f"Gasoil: uzywam Yahoo '{sym}' ({len(series)} notowan)")
        return series

    log.warning("Gasoil: Yahoo nie dal danych, probuje stooq...")
    series = stooq_csv_series(STOOQ_GASOIL, start) or stooq_last_json(STOOQ_GASOIL)
    if series:
        log.info(f"Gasoil: uzywam stooq '{STOOQ_GASOIL}' ({len(series)} notowan)")
        return series

    # Ostatnia deska ratunku: scanner TradingView. Zwraca migawke bez daty,
    # wiec przypisujemy dzien biezacy i tylko w dni robocze (w weekend oddalby
    # piatkowe zamkniecie pod sobotnia data).
    log.warning("Gasoil: stooq nie dal danych, probuje scanner TradingView...")
    close, desc = tradingview_quote(TV_GASOIL_SYMBOL, GASOIL_MIN, GASOIL_MAX)
    if close is None:
        return {}
    today = date.today()
    if today.weekday() >= 5:
        log.info("Gasoil: weekend — scanner oddalby piatkowe zamkniecie, pomijam")
        return {}
    log.info(f"Gasoil: scanner '{TV_GASOIL_SYMBOL}' ({desc}) — tylko {today}")
    return {today.isoformat(): close}


def get_usdpln(start):
    """Seria USD/PLN. Yahoo, zapasowo NBP, na koncu stooq."""
    log.info("USD/PLN — szukam symbolu w Yahoo Finance...")
    # Bez kontroli waluty: pasmo 2,5-6,0 i tak jednoznacznie identyfikuje kurs
    # USD/PLN, a Yahoo raportuje walute par walutowych niekonsekwentnie.
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

def main(refresh_from=None):
    """
    refresh_from: gdy podane, pobiera od tej daty i NADPISUJE istniejace wpisy
    z tego zakresu. Sluzy do swiadomej, jednorazowej podmiany zrodla — np.
    zastapienia blokku ze stooq notowaniami ICE. Bez tego argumentu odswiezane
    jest tylko okno BACKFILL_LOOKBACK_DAYS, zeby cron nie przepisywal historii
    po cichu przy kazdym przebiegu.
    """
    log.info("=" * 50)
    log.info("START — ICE Gasoil + USD/PLN")
    if refresh_from:
        log.info(f"TRYB PODMIANY: nadpisuje istniejace wpisy od {refresh_from}")

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
    if refresh_from:
        start = refresh_from
        refresh_boundary = refresh_from.isoformat()
    else:
        start = min(last_date + timedelta(days=1),
                    date.today() - timedelta(days=BACKFILL_LOOKBACK_DAYS))
        refresh_boundary = (date.today() - timedelta(days=BACKFILL_LOOKBACK_DAYS)).isoformat()
    log.info(f"Ostatni wpis: {last_date}, pobieram od {start} do {date.today()}")

    gasoil = get_gasoil(start)
    usdpln = get_usdpln(start)

    # Laczymy PO DACIE. Poprzednia wersja brala date z ICE i doklejala kurs
    # z dowolnego innego dnia, co cicho mieszalo notowania z roznych sesji.
    by_date = {e["date"]: e for e in history}
    added = refreshed = 0

    for d in sorted(set(gasoil) & set(usdpln)):
        ice_usd, fx = gasoil[d], usdpln[d]
        entry = {
            "date": d,
            "ice_usd_tonne": round(ice_usd, 2),
            "usdpln": round(fx, 5),
            "ice_pln_1000l": round(ice_usd * DENSITY * fx, 2),
        }

        old = by_date.get(d)
        if old is None:
            history.append(entry)
            by_date[d] = entry
            added += 1
            log.info(f"  +{d}: {ice_usd:.2f} USD/t x {fx:.5f} = {entry['ice_pln_1000l']} PLN/1000l")
            continue

        # Wpis zlapany w trakcie sesji zamarzalby na zawsze, bo dawniej kazda
        # znana data byla po prostu pomijana. Odswiezamy wartosc powyzej
        # refresh_boundary, gdy zrodlo podaje inna — TradingView jest tu
        # autorytatywne. Starszych wpisow nie ruszamy.
        if d >= refresh_boundary and old.get("ice_usd_tonne") != entry["ice_usd_tonne"]:
            log.info(f"  ~{d}: {old.get('ice_usd_tonne')} -> {entry['ice_usd_tonne']} USD/t "
                     f"(korekta do zamkniecia)")
            old.update(entry)
            refreshed += 1

    only_gasoil = sorted(set(gasoil) - set(usdpln))
    only_fx = sorted(set(usdpln) - set(gasoil))
    if only_gasoil:
        log.info(f"Pominieto {len(only_gasoil)} dni bez kursu USD/PLN: {only_gasoil[:5]}")
    if only_fx:
        log.info(f"Pominieto {len(only_fx)} dni bez notowania gasoilu: {only_fx[:5]}")

    if added or refreshed:
        history.sort(key=lambda e: e["date"], reverse=True)
        save_history(history)
        log.info(f"KONIEC — dopisano {added}, skorygowano {refreshed} "
                 f"(ostatni: {history[0]['date']})")
        return

    # Nic nie dopisano. Jesli archiwum jest swieze, to normalne (weekend,
    # swieto). Jesli stare — zadne zrodlo nie dziala i trzeba o tym glosno
    # powiedziec, zamiast konczyc kodem 0 (co robila poprzednia wersja, gdy
    # stooq zwrocil poprawny JSON z pusta lista "symbols").
    age = (date.today() - last_date).days
    if age > STALE_AFTER_DAYS:
        log.error(f"Brak nowych danych, a ostatni wpis ma {age} dni "
                  f"({last_date}). Zadne zrodlo nie odpowiedzialo.")
        sys.exit(1)

    log.info(f"Brak nowych notowan (ostatni wpis sprzed {age} dni) — to normalne")


if __name__ == "__main__":
    _from = None
    if "--refresh-from" in sys.argv:
        _raw = sys.argv[sys.argv.index("--refresh-from") + 1]
        try:
            _from = datetime.strptime(_raw, "%Y-%m-%d").date()
        except ValueError:
            log.error(f"--refresh-from: zla data '{_raw}', oczekiwano RRRR-MM-DD")
            sys.exit(2)
    main(_from)
