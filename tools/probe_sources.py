#!/usr/bin/env python3
"""Runda 4: szukamy PRAWDZIWEGO ICE Low Sulphur Gasoil (nie proxy)."""
from datetime import date, datetime, timedelta
import requests, json

OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
H={"User-Agent":UA,"Accept":"*/*","Accept-Language":"en-US,en;q=0.9"}
log("="*78); log("PROBE runda 4 — PRAWDZIWY ICE gasoil —", date.today().isoformat()); log("="*78)

def probe(name, url, headers=None, note=""):
    try:
        r=requests.get(url,timeout=30,headers=headers or H)
        body=r.text[:230].replace("\n"," ").replace("\r","")
        log(f"  [{r.status_code}] {name:38s} len={len(r.text):8d} :: {body}")
        return r
    except Exception as e:
        log(f"  [ERR] {name:38s} {type(e).__name__}: {str(e)[:70]}")
        return None

log("\n### A. theice.com — oficjalne dane opoznione")
probe("ICE getContracts g/oil p=254","https://www.theice.com/marketdata/DelayedMarkets.shtml?getContractsAsJson=&productId=254&hubId=403")
probe("ICE getContracts p=4331","https://www.theice.com/marketdata/DelayedMarkets.shtml?getContractsAsJson=&productId=4331&hubId=6535")
probe("ICE HistoricalChart 254","https://www.theice.com/marketdata/DelayedMarkets.shtml?getHistoricalChartDataAsJson=&marketId=5500098&historicalSpan=3")
probe("ICE productGuide spec","https://www.theice.com/api/productguide/spec/34361119")
probe("ICE productGuide search","https://www.theice.com/api/productguide/search?query=gasoil")

log("\n### B. Nasdaq Data Link (dawny Quandl) — CHRIS/ICE_G1")
for ds in ["CHRIS/ICE_G1","CHRIS/ICE_G2"]:
    probe(f"quandl {ds}", f"https://www.quandl.com/api/v3/datasets/{ds}.json?rows=5")
    probe(f"nasdaq {ds}",  f"https://data.nasdaq.com/api/v3/datasets/{ds}.json?rows=5")

log("\n### C. TradingView — ICEEUR:ULS1! (Low Sulphur Gasoil)")
try:
    r=requests.post("https://scanner.tradingview.com/symbol",timeout=30,headers=H,
        params={"symbol":"ICEEUR:ULS1!","fields":"close,update_mode,currency_code","no_404":"true"})
    log(f"  [scanner GET-params] {r.status_code} :: {r.text[:200]}")
except Exception as e: log("  scanner err",e)
probe("TV scanner symbol","https://scanner.tradingview.com/symbol?symbol=ICEEUR%3AULS1%21&fields=close%2Ccurrency_code&no_404=true")
probe("TV history ULS1!","https://history.tradingview.com/history?symbol=ICEEUR%3AULS1%21&resolution=D&from=1780000000&to=1790000000")

log("\n### D. investing.com — endpointy wykresowe (inne niz strona)")
NOW=int(datetime.now().timestamp()); FROM=NOW-120*86400
for host in ["tvc4.investing.com","tvc6.investing.com"]:
    probe(f"{host} history 8833",
          f"https://{host}/1/1/1/1/1/history?symbol=8833&resolution=D&from={FROM}&to={NOW}",
          headers={**H,"Referer":"https://tvc-invdn-com.investing.com/"})

log("\n### E. polskie portale kwotujace gasoil")
probe("biznesradar gasoil","https://www.biznesradar.pl/notowania/GASOIL")
probe("bankier surowce","https://www.bankier.pl/gielda/notowania/surowce")
probe("money.pl surowce","https://www.money.pl/gielda/surowce/")
probe("stooq strona lf.f (kontrola)","https://stooq.pl/q/?s=lf.f")

open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
