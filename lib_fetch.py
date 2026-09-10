#!/usr/bin/env python3
"""
lib_fetch.py — wspolne pobieranie notowan dla fetch_ice.py i fetch_wibor.py.

Wczesniej fetch_stooq_json() byla skopiowana 1:1 w obu plikach, wiec awaria
stooq z 4 czerwca 2026 wymagala poprawki w dwoch miejscach.

Kazda funkcja zwraca SERIE {"RRRR-MM-DD": wartosc}, a nie pojedynczy odczyt.
Dzieki temu wywolujacy moze uzupelnic dowolnie dluga luke jednym zapytaniem.
"""
import csv
import io
import json
import logging
import re
from datetime import date, datetime, timedelta

import requests

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 20


# ===== YAHOO FINANCE (yfinance) =====

def yf_series(symbol, start):
    """Notowania dzienne z Yahoo Finance. Zwraca {data: close} lub {} przy bledzie."""
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance nie zainstalowany")
        return {}

    try:
        hist = yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=(date.today() + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
    except Exception as e:
        log.warning(f"yfinance {symbol}: {type(e).__name__}: {e}")
        return {}

    out = {}
    for ts, row in hist.iterrows():
        close = row.get("Close")
        if close is None or close != close:  # NaN
            continue
        out[ts.date().isoformat()] = float(close)
    return out


def pick_symbol(candidates, start, lo, hi):
    """
    Probuje kolejne symbole i zwraca (symbol, seria) dla pierwszego, ktory da
    dane w wiarygodnym pasmie lo..hi.

    Yahoo nie ma stabilnego, udokumentowanego symbolu ciaglego dla ICE Low
    Sulphur Gasoil, a nazwy kontraktow potrafia sie zmieniac przy rolowaniu.
    Zamiast zaszywac jeden symbol na sztywno, sprawdzamy liste i logujemy
    zwyciezce — dzieki temu skrypt sam sie naprawia, gdy symbol sie zmieni.
    Pasmo lo..hi chroni przed cichym wzieciem instrumentu w zlej jednostce
    (np. HO=F jest w USD/galon, nie USD/tone — poziom cen rozjechalby premie).
    """
    for sym in candidates:
        series = yf_series(sym, start)
        if not series:
            log.info(f"  {sym}: brak danych")
            continue
        last = series[max(series)]
        if not (lo <= last <= hi):
            log.info(f"  {sym}: ostatnia wartosc {last} poza pasmem {lo}-{hi}, odrzucam")
            continue
        log.info(f"  {sym}: OK — {len(series)} notowan, ostatnie {last}")
        return sym, series
    return None, {}


# ===== STOOQ (zapasowo) =====

def stooq_csv_series(symbol, start):
    """
    Historia dzienna ze stooq w CSV (/q/d/l/). W odroznieniu od endpointu /q/l/
    zwraca cala serie, wiec nadaje sie do uzupelnienia luki.
    """
    url = f"https://stooq.pl/q/d/l/?s={symbol}&i=d"
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"stooq CSV {symbol}: {type(e).__name__}: {e}")
        return {}

    text = resp.text.strip()
    if not text or text.lower().startswith("brak danych") or "," not in text:
        log.warning(f"stooq CSV {symbol}: pusta lub niepoprawna odpowiedz")
        return {}

    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        raw_date = (row.get("Data") or row.get("Date") or "").strip()
        raw_close = (row.get("Zamkniecie") or row.get("Close") or "").strip()
        if not raw_date or not raw_close:
            continue
        try:
            d = datetime.strptime(raw_date, "%Y-%m-%d").date()
            if d >= start:
                out[d.isoformat()] = float(raw_close)
        except ValueError:
            continue
    return out


def stooq_last_json(symbol):
    """Ostatnie notowanie ze stooq (/q/l/). Zwraca {data: close} lub {}."""
    url = f"https://stooq.pl/q/l/?s={symbol}&f=sd2t2ohlcvn&h=&e=json"
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
        # stooq potrafi zwrocic niepoprawny JSON: "volume":,
        data = json.loads(re.sub(r'"volume":,', '"volume":null,', resp.text))
    except Exception as e:
        log.warning(f"stooq JSON {symbol}: {type(e).__name__}: {e}")
        return {}

    symbols = data.get("symbols") or []
    if not symbols:
        return {}
    s = symbols[0]
    close, d = s.get("close"), s.get("date")
    if not close or not d:
        return {}
    try:
        return {d: float(close)}
    except (TypeError, ValueError):
        # stooq wstawia "N/D" gdy nie ma notowania
        return {}


# ===== NBP (zapasowo dla USD/PLN) =====

def nbp_usdpln_series(start):
    """
    Kurs sredni USD/PLN z oficjalnego API NBP (tabela A).

    Uwaga: NBP publikuje kurs sredni ok. 12:00, wiec rozni sie o ok. 0,1%
    od kursu zamkniecia. Przy 3300 PLN/1000l to ok. 3 zl roznicy w wyniku.
    Zrodlo zapasowe — uzywane tylko gdy Yahoo zawiedzie.
    """
    end = date.today()
    # API NBP przyjmuje maksymalnie 93 dni na zapytanie
    out = {}
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=92), end)
        url = (f"https://api.nbp.pl/api/exchangerates/rates/a/usd/"
               f"{cursor.isoformat()}/{chunk_end.isoformat()}/?format=json")
        try:
            resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
            if resp.status_code == 404:  # brak danych w tym zakresie
                cursor = chunk_end + timedelta(days=1)
                continue
            resp.raise_for_status()
            for r in resp.json().get("rates", []):
                out[r["effectiveDate"]] = float(r["mid"])
        except Exception as e:
            log.warning(f"NBP {cursor}..{chunk_end}: {type(e).__name__}: {e}")
        cursor = chunk_end + timedelta(days=1)
    return out
