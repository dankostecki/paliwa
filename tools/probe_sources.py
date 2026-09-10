#!/usr/bin/env python3
"""Runda 5: HISTORIA ICE Low Sulphur Gasoil (ICEEUR:ULS1! dziala na TV scanner)."""
from datetime import date, datetime, timedelta
import requests, json
OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
H={"User-Agent":UA,"Accept":"application/json, text/plain, */*"}
log("="*78); log("PROBE runda 5 — HISTORIA gasoilu —", date.today().isoformat()); log("="*78)

def g(name,url,headers=None,cut=240):
    try:
        r=requests.get(url,timeout=30,headers=headers or H)
        log(f"  [{r.status_code}] {name:40s} len={len(r.text):8d} :: {r.text[:cut]}")
        return r
    except Exception as e:
        log(f"  [ERR] {name:40s} {type(e).__name__}: {str(e)[:60]}"); return None

log("\n### A. TradingView scanner — ile pol da sie wyciagnac")
FIELDS=("close,open,high,low,currency_code,description,pricescale,update_mode,"
        "change,change_abs,Perf.W,Perf.1M,Perf.3M,Perf.YTD,"
        "close|1W,close|1M,High.3M,Low.3M,High.6M,Low.6M,High.All,Low.All")
r=g("TV scanner pelne pola",
    f"https://scanner.tradingview.com/symbol?symbol=ICEEUR%3AULS1%21&fields={FIELDS}&no_404=true",cut=700)

log("\n### B. TradingView — inne kontrakty i endpointy historii")
for s in ["ICEEUR%3AULS2%21","ICEEUR%3AULS1%21"]:
    g(f"TV {s}", f"https://scanner.tradingview.com/symbol?symbol={s}&fields=close,description&no_404=true")
for u,n in [("https://udf.tradingview.com/udf/history?symbol=ICEEUR:ULS1!&resolution=D&from=1770000000&to=1789000000","udf.tradingview"),
            ("https://demo-feed-data.tradingview.com/history?symbol=ICEEUR:ULS1!&resolution=D&from=1770000000&to=1789000000","demo-feed"),
            ("https://symbol-search.tradingview.com/symbol_search/v3/?text=gasoil&type=futures","TV symbol search")]:
    g(n,u,cut=300)

log("\n### C. ICE productguide — kopiemy glebiej (spec 34361119 dziala)")
r=g("ICE spec",  "https://www.theice.com/api/productguide/spec/34361119",cut=120)
if r and r.status_code==200:
    try:
        d=r.json()
        log("   klucze:", ", ".join(list(d.keys())[:28]))
        for k in ("productId","hubId","marketId","symbol","displayName","settlementType"):
            if k in d: log(f"   {k} = {d[k]}")
    except Exception as e: log("   parse err",e)
for u,n in [("https://www.theice.com/marketdata/DelayedMarkets.shtml?getContractsAsJson=&productId=5817&hubId=9373","ICE contracts 5817/9373"),
            ("https://www.theice.com/marketdata/api/productData?productId=5817","ICE productData")]:
    g(n,u,headers={**H,"Referer":"https://www.theice.com/marketdata/DelayedMarkets.shtml"},cut=200)

log("\n### D. FT markets — otwarty endpoint serii czasowych")
try:
    r=requests.post("https://markets.ft.com/data/chartapi/series",timeout=30,
      headers={**H,"Content-Type":"application/json","Referer":"https://markets.ft.com/data/"},
      json={"days":180,"dataNormalized":False,"dataPeriod":"Day","dataInterval":1,
            "realtime":False,"returnDateType":"ISO8601",
            "elements":[{"Label":"g","Type":"price","Symbol":"IOM:GAS","OverlayIndicators":[],"Params":{}}]})
    log(f"  [FT] {r.status_code} len={len(r.text)} :: {r.text[:300]}")
except Exception as e: log("  FT err",type(e).__name__,str(e)[:60])

log("\n### E. inne")
g("WSJ gasoil","https://www.wsj.com/market-data/quotes/futures/UK/IFEU/LFN26/historical-prices/download?MOD=mw_quote&startDate=06/01/2026&endDate=09/10/2026",cut=200)
g("barchart proxy","https://www.barchart.com/proxies/core-api/v1/quotes/get?symbols=LF*0&fields=lastPrice,tradeTime",cut=200)
g("oilprice","https://oilprice.com/rss/main",cut=150)

open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
