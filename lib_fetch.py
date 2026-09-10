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
import time
from datetime import date, datetime, timedelta, timezone

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


def yf_meta(symbol):
    """Waluta i nazwa instrumentu z Yahoo. Zwraca (currency, name), moga byc None."""
    try:
        import yfinance as yf
        fi = yf.Ticker(symbol).fast_info
        return (getattr(fi, "currency", None), getattr(fi, "quote_type", None))
    except Exception:
        return (None, None)


def pick_symbol(candidates, start, lo, hi, currency=None):
    """
    Probuje kolejne symbole i zwraca (symbol, seria) dla pierwszego, ktory da
    dane w wiarygodnym pasmie lo..hi (i w oczekiwanej walucie, jesli podana).

    Yahoo nie ma stabilnego, udokumentowanego symbolu ciaglego dla ICE Low
    Sulphur Gasoil, a nazwy kontraktow potrafia sie zmieniac przy rolowaniu.
    Zamiast zaszywac jeden symbol na sztywno, sprawdzamy liste i logujemy
    zwyciezce — dzieki temu skrypt sam sie naprawia, gdy symbol sie zmieni.

    Pasmo lo..hi jest tu glowna ochrona przed wzieciem zlego instrumentu.
    NIE da sie tego zastapic porownaniem z ostatnia wartoscia w archiwum:
    gasoil potrafi zmienic sie o 94% w ciagu 3 miesiecy (2026-01-26 -> 2026-04-29
    w tym wlasnie archiwum), wiec kazdy prog procentowy dawalby falszywe alarmy.
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

        cur, qtype = yf_meta(sym)
        if currency and cur and cur.upper() != currency.upper():
            log.warning(f"  {sym}: waluta {cur}, oczekiwano {currency} — odrzucam")
            continue

        log.info(f"  {sym}: OK — {len(series)} notowan, ostatnie {last} "
                 f"(waluta={cur or '?'}, typ={qtype or '?'})")
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


# ===== TRADINGVIEW =====

TV_SCANNER = "https://scanner.tradingview.com/symbol"


def tradingview_quote(symbol, lo=None, hi=None):
    """
    Biezace notowanie z publicznego scannera TradingView.

    Jedyne znalezione dzialajace zrodlo prawdziwego ICE Low Sulphur Gasoil
    (ICEEUR:ULS1!). Yahoo nie ma tego kontraktu w ogole, stooq postawil
    zapore anty-botowa, investing.com i Barchart zwracaja 403.

    UWAGA: zwraca tylko biezacy odczyt, bez serii historycznej — dlatego
    uzupelnia archiwum wylacznie o dzien dzisiejszy.

    Zwraca (close, description) albo (None, None).
    """
    try:
        r = requests.get(
            TV_SCANNER,
            params={"symbol": symbol,
                    "fields": "close,open,high,low,description,update_mode",
                    "no_404": "true"},
            timeout=TIMEOUT, headers=HEADERS)
        r.raise_for_status()
        d = r.json() or {}
    except Exception as e:
        log.warning(f"TradingView {symbol}: {type(e).__name__}: {e}")
        return None, None

    close = d.get("close")
    desc = d.get("description")
    if close is None:
        log.warning(f"TradingView {symbol}: brak pola close")
        return None, None
    close = float(close)

    if lo is not None and not (lo <= close <= hi):
        log.warning(f"TradingView {symbol}: {close} poza pasmem {lo}-{hi}, odrzucam")
        return None, None

    log.info(f"TradingView {symbol}: {close} ({desc}, {d.get('update_mode')})")
    return close, desc


def tradingview_history(symbol, exchange, start, lo=None, hi=None, n_bars=400):
    """
    Historia dzienna z TradingView. Zwraca {"RRRR-MM-DD": close} — ten sam
    kontrakt co yf_series() i stooq_csv_series(), wiec wywolujacy nie musi
    tego traktowac inaczej.

    Rozmawiamy wprost protokolem WebSocket, ktorym karmia sie wykresy
    TradingView. Alternatywa (biblioteka tvdatafeed) wymagalaby instalacji
    z gita — pip install tvdatafeed nie przechodzi z PyPI — a daje dokladnie
    te same liczby, wiec zostaje samo websocket-client.

    DATOWANIE: ICE otwiera sesje poniedzialkowa w niedziele o 22:00, a
    TradingView znakuje slupki czasem OTWARCIA. Bez korekty caly poniedzialek
    laduje pod niedziela — w surowej serii widac pon=0, NDZ=60. Slupek
    otwarty w niedziele przesuwamy wiec na poniedzialek.

    Zweryfikowane wobec danych referencyjnych uzytkownika (arkusz Google,
    2026-01-09..2026-03-05): 38/40 wartosci identycznych co do grosza,
    40/40 w tolerancji 0,5%, sredni blad 0,02%.
    """
    try:
        from websocket import create_connection
    except ImportError:
        log.warning("websocket-client nie zainstalowany")
        return {}

    def _sess(prefix):
        import random, string
        return prefix + "_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))

    def _frame(method, params):
        body = json.dumps({"m": method, "p": params}, separators=(",", ":"))
        return f"~m~{len(body)}~m~{body}"

    raw = ""
    try:
        ws = create_connection(
            "wss://data.tradingview.com/socket.io/websocket?from=chart%2F",
            header=[f"User-Agent: {HEADERS['User-Agent']}"],
            origin="https://www.tradingview.com", timeout=30)
        cs = _sess("cs")
        for method, params in [
            ("set_auth_token", ["unauthorized_user_token"]),
            ("chart_create_session", [cs, ""]),
            ("resolve_symbol", [cs, "sds_sym_1",
                                '={"symbol":"%s:%s","adjustment":"splits"}' % (exchange, symbol)]),
            ("create_series", [cs, "sds_1", "s1", "sds_sym_1", "1D", n_bars, ""]),
        ]:
            ws.send(_frame(method, params))

        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                chunk = ws.recv()
            except Exception:
                break
            raw += chunk
            if "series_completed" in raw:
                break
            # serwer wysyla ~h~N jako heartbeat i oczekuje odbicia
            for ping in re.findall(r"~m~\d+~m~(~h~\d+)", chunk):
                ws.send(f"~m~{len(ping)}~m~{ping}")
        ws.close()
    except Exception as e:
        log.warning(f"TradingView {exchange}:{symbol}: {type(e).__name__}: {e}")
        return {}

    if "series_completed" not in raw:
        log.warning(f"TradingView {exchange}:{symbol}: seria nie zostala zamknieta "
                    f"(odebrano {len(raw)} znakow)")

    out, skipped = {}, 0
    for blob in re.findall(r'"s":\[(.*?)\],"ns"', raw, re.S):
        for m in re.finditer(r'\{"i":\d+,"v":\[([0-9eE\.\+\-,]+)\]\}', blob):
            v = [float(x) for x in m.group(1).split(",")]
            if len(v) < 5:
                continue
            ts = datetime.fromtimestamp(v[0], tz=timezone.utc)
            d = ts.date()
            if ts.weekday() == 6:        # niedziela 22:00 = otwarcie poniedzialku
                d = d + timedelta(days=1)
            if d < start:
                continue
            close = v[4]
            if lo is not None and not (lo <= close <= hi):
                skipped += 1
                continue
            out[d.isoformat()] = close

    if skipped:
        log.warning(f"TradingView {symbol}: pominieto {skipped} slupkow poza pasmem {lo}-{hi}")
    if not out:
        log.warning(f"TradingView {exchange}:{symbol}: nie sparsowano zadnego slupka")
    else:
        log.info(f"TradingView {exchange}:{symbol}: {len(out)} notowan od {start}")
    return out


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
