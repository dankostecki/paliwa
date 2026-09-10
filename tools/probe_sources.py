#!/usr/bin/env python3
"""Runda 8: ostatnia proba historii + test pelnego pobrania przez TradingView."""
from datetime import date
import requests, json, re
OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
H={"User-Agent":UA,"Accept":"application/json, text/html;q=0.9,*/*;q=0.8"}
log("="*78); log("PROBE runda 8 —", date.today().isoformat()); log("="*78)

log("\n### A. ostatnie kandydatury na HISTORIE dzienna")
tries=[
 ("businessinsider hist","https://markets.businessinsider.com/api/HistoricPriceList/Get?instrumentType=Commodity&tkData=1%2C10%2C0%2C333&from=20260601&to=20260910"),
 ("businessinsider gasoil","https://markets.businessinsider.com/commodities/gasoil-price"),
 ("finanzen.net gasoil","https://www.finanzen.net/rohstoffe/gasoil-preis"),
 ("finanzen.net hist","https://www.finanzen.net/rohstoffe/historisch/gasoil/usd"),
 ("boerse.de","https://www.boerse.de/rohstoffe/Gasoil-Preis/XC0009677409"),
 ("investing api v2","https://api.investing.com/api/financialdata/historical/8833?start-date=2026-06-01&end-date=2026-09-10&time-frame=Daily"),
 ("wsj quote","https://www.wsj.com/market-data/quotes/futures/UK/IFEU/LF00"),
 ("TV scanner futures scan","https://scanner.tradingview.com/futures/scan"),
]
for n,u in tries:
    try:
        r=requests.get(u,timeout=30,headers=H)
        body=r.text[:200].replace("\n"," ")
        log(f"  [{r.status_code}] {n:26s} len={len(r.text):8d} :: {body}")
    except Exception as e:
        log(f"  [ERR] {n:26s} {type(e).__name__}: {str(e)[:55]}")

log("\n### B. TEST: pelne pobranie przez TradingView + yfinance (to co wdrozymy)")
try:
    r=requests.get("https://scanner.tradingview.com/symbol",
        params={"symbol":"ICEEUR:ULS1!",
                "fields":"close,open,high,low,description,update_mode,pricescale","no_404":"true"},
        timeout=30,headers=H)
    tv=r.json()
    log(f"  TradingView ICEEUR:ULS1! -> {tv}")
    gasoil=tv.get("close")
except Exception as e:
    gasoil=None; log("  TV blad:",type(e).__name__,str(e)[:80])

try:
    import yfinance as yf
    h=yf.Ticker("USDPLN=X").history(period="5d")
    fx=float(h["Close"].iloc[-1]); fxd=h.index[-1].date().isoformat()
    log(f"  USDPLN=X -> {fx:.5f} @{fxd}")
except Exception as e:
    fx=None; log("  FX blad:",type(e).__name__,str(e)[:80])

if gasoil and fx:
    pln=round(gasoil*0.845*fx,2)
    log(f"  WYNIK: {gasoil} USD/t x 0.845 x {fx:.5f} = {pln} PLN/1000l")
    try:
        ice=json.load(open("data/ice_history.json"))
        log(f"  ostatni wpis w archiwum: {ice[0]['date']} = {ice[0]['ice_pln_1000l']} PLN/1000l "
            f"({ice[0]['ice_usd_tonne']} USD/t)")
        log(f"  zmiana USD/t przez luke: {(gasoil/ice[0]['ice_usd_tonne']-1)*100:+.1f}%")
    except Exception as e: log("  ",e)

open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
