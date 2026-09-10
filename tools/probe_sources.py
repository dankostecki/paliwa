#!/usr/bin/env python3
"""Runda 2: szukamy zrodla dla ICE Low Sulphur Gasoil."""
import json
from datetime import date
import requests

OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
log("="*78); log("PROBE runda 2 —", date.today().isoformat()); log("="*78)

# ---------- A. wyszukiwarka symboli Yahoo ----------
log("\n### A. Yahoo symbol search — co Yahoo w ogole ma")
for q in ["gasoil", "low sulphur gasoil", "ICE gasoil", "gas oil futures", "diesel futures"]:
    try:
        r = requests.get("https://query2.finance.yahoo.com/v1/finance/search",
                         params={"q": q, "quotesCount": 12, "newsCount": 0},
                         timeout=25, headers={"User-Agent": UA})
        if r.status_code != 200:
            log(f"  '{q}': HTTP {r.status_code}"); continue
        qs = r.json().get("quotes", [])
        log(f"  '{q}': {len(qs)} trafien")
        for x in qs:
            log("     %-16s %-10s %-9s %s" % (x.get("symbol"), x.get("quoteType"),
                                              x.get("exchange"), (x.get("shortname") or "")[:44]))
    except Exception as e:
        log(f"  '{q}': {type(e).__name__}: {str(e)[:70]}")

# ---------- B. datowane kontrakty NYMEX 7F ----------
log("\n### B. datowane kontrakty NYMEX (European Low Sulphur Gasoil, root 7F)")
try:
    import yfinance as yf
    MC = {9:"U",10:"V",11:"X",12:"Z",1:"F",2:"G",3:"H",4:"J",5:"K",6:"M",7:"N",8:"Q"}
    cands = []
    for root in ["7F", "LF", "QS"]:
        for m in [9,10,11,12]:
            cands.append(f"{root}{MC[m]}26.NYM")
        cands.append(f"{root}=F")
    for s in cands:
        try:
            h = yf.Ticker(s).history(period="5d")
            if len(h):
                log(f"  OK   {s:14s} n={len(h)} last={h['Close'].iloc[-1]:.3f} @{h.index[-1].date()}")
            else:
                log(f"  --   {s:14s} pusta")
        except Exception as e:
            log(f"  ERR  {s:14s} {type(e).__name__}")
except Exception as e:
    log("  yfinance blad:", e)

# ---------- C. co dokladnie zwraca stooq CSV ----------
log("\n### C. stooq CSV — pelna tresc odpowiedzi (796 B)")
s = requests.Session(); s.headers.update({"User-Agent": UA})
try:
    r = s.get("https://stooq.pl/q/d/l/?s=lf.f&i=d", timeout=25)
    log(f"  HTTP {r.status_code} ct={r.headers.get('content-type')}")
    log("  TRESC: " + r.text[:700].replace("\n", " "))
except Exception as e:
    log(f"  {type(e).__name__}: {e}")

log("\n### C2. stooq z cookie: najpierw strona instrumentu, potem CSV")
try:
    p = s.get("https://stooq.pl/q/?s=lf.f", timeout=25)
    log(f"  strona: HTTP {p.status_code} len={len(p.text)} cookies={list(s.cookies.keys())}")
    r2 = s.get("https://stooq.pl/q/d/l/?s=lf.f&i=d", timeout=25,
               headers={"Referer": "https://stooq.pl/q/?s=lf.f"})
    log(f"  CSV po cookie: HTTP {r2.status_code} len={len(r2.text)} :: {r2.text[:200].replace(chr(10),' ')}")
except Exception as e:
    log(f"  {type(e).__name__}: {e}")

# ---------- D. inne darmowe zrodla ----------
log("\n### D. inne zrodla")
tries = [
 ("EIA Rotterdam ULSD (bez klucza)", "https://api.eia.gov/v2/petroleum/pri/spt/data/?frequency=daily&data[0]=value&length=3"),
 ("Yahoo chart 7FV26.NYM", "https://query1.finance.yahoo.com/v8/finance/chart/7FV26.NYM?range=1mo&interval=1d"),
 ("Yahoo chart LF=F",      "https://query1.finance.yahoo.com/v8/finance/chart/LF=F?range=1mo&interval=1d"),
 ("Barchart LF*0",         "https://www.barchart.com/futures/quotes/LF*0"),
 ("marketwatch gasoil",    "https://www.marketwatch.com/investing/future/lf00"),
]
for name, url in tries:
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": UA})
        log(f"  {name:32s} HTTP {r.status_code} len={len(r.text):7d} :: {r.text[:130].replace(chr(10),' ')}")
    except Exception as e:
        log(f"  {name:32s} {type(e).__name__}: {str(e)[:60]}")

open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
log("\nzapisano")
