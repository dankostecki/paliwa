#!/usr/bin/env python3
"""Runda 3: arkusz Google uzytkownika + legalne darmowe zrodla gasoilu."""
from datetime import date
import requests, json

OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
log("="*78); log("PROBE runda 3 —", date.today().isoformat()); log("="*78)

SHEET=("https://docs.google.com/spreadsheets/d/"
       "1FRfB6Xctk00eTAyR_8MM3tM1D1UBPYO4F4yZFlhlzMM/export?format=csv")
log("\n### A. Arkusz Google (zrodlo pierwotnego importu w fetch_ice.py)")
try:
    r=requests.get(SHEET,timeout=30,headers={"User-Agent":UA})
    log(f"  HTTP {r.status_code} len={len(r.text)} ct={r.headers.get('content-type')}")
    if r.status_code==200 and "text/csv" in (r.headers.get("content-type") or ""):
        lines=r.text.strip().splitlines()
        log(f"  wierszy: {len(lines)}")
        log("  NAGLOWEK: "+lines[0][:150])
        log("  PIERWSZE 3:"); [log("    "+l[:150]) for l in lines[1:4]]
        log("  OSTATNIE 6:"); [log("    "+l[:150]) for l in lines[-6:]]
    else:
        log("  TRESC: "+r.text[:250].replace("\n"," "))
except Exception as e:
    log(f"  {type(e).__name__}: {str(e)[:120]}")

log("\n### B. inne legalne darmowe zrodla dla gasoilu / ropy")
tries=[
 ("AlphaVantage BRENT demo","https://www.alphavantage.co/query?function=BRENT&interval=daily&apikey=demo"),
 ("EIA bez klucza","https://api.eia.gov/v2/petroleum/pri/spt/data/?frequency=daily&length=2"),
 ("EC Oil Bulletin","https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"),
 ("Yahoo ^SPGSGOP (indeks gasoil)","https://query1.finance.yahoo.com/v8/finance/chart/%5ESPGSGOP?range=1mo&interval=1d"),
 ("Yahoo HO=F","https://query1.finance.yahoo.com/v8/finance/chart/HO=F?range=5d&interval=1d"),
]
for name,url in tries:
    try:
        r=requests.get(url,timeout=30,headers={"User-Agent":UA})
        log(f"  {name:32s} HTTP {r.status_code} len={len(r.text):8d} :: {r.text[:160].replace(chr(10),' ')}")
    except Exception as e:
        log(f"  {name:32s} {type(e).__name__}: {str(e)[:60]}")

log("\n### C. korelacja HO=F vs archiwum ICE (czy HO moglby sluzyc za proxy)")
try:
    import yfinance as yf
    h=yf.Ticker("HO=F").history(start="2026-01-09",end="2026-06-06")
    ho={d.date().isoformat():float(v) for d,v in zip(h.index,h["Close"])}
    ice=json.load(open("data/ice_history.json"))
    pairs=[(e["ice_usd_tonne"],ho[e["date"]]) for e in ice if e["date"] in ho]
    log(f"  wspolnych dni: {len(pairs)}")
    if len(pairs)>5:
        n=len(pairs); sx=sum(p[0] for p in pairs); sy=sum(p[1] for p in pairs)
        mx,my=sx/n,sy/n
        cov=sum((a-mx)*(b-my) for a,b in pairs)
        vx=sum((a-mx)**2 for a,b in pairs)**.5; vy=sum((b-my)**2 for a,b in pairs)**.5
        log(f"  korelacja Pearsona ICE(USD/t) vs HO=F(USD/gal): {cov/(vx*vy):.4f}")
        log(f"  sredni przelicznik USD/t na USD/gal: {mx/my:.2f}")
        for a,b in pairs[:5]: log(f"    ICE={a:8.2f}  HO={b:7.4f}  iloraz={a/b:7.2f}")
        for a,b in pairs[-5:]: log(f"    ICE={a:8.2f}  HO={b:7.4f}  iloraz={a/b:7.2f}")
except Exception as e:
    log(f"  {type(e).__name__}: {str(e)[:100]}")

open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
