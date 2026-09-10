#!/usr/bin/env python3
"""Runda 6: HISTORIA — FT symbol lookup + portale DE."""
from datetime import date
import requests, json
OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
H={"User-Agent":UA,"Accept":"application/json, text/plain, */*"}
log("="*78); log("PROBE runda 6 — HISTORIA —", date.today().isoformat()); log("="*78)

log("\n### A. FT — wyszukiwarka symboli")
found=[]
for q in ["gas oil","gasoil","low sulphur gasoil","ICE gasoil"]:
    try:
        r=requests.get("https://markets.ft.com/data/searchapi/searchsecurities",
                       params={"query":q},timeout=30,headers=H)
        log(f"  '{q}': HTTP {r.status_code} len={len(r.text)}")
        if r.status_code==200:
            try:
                d=r.json().get("data",{}).get("security",[])
                for x in d[:10]:
                    log(f"     {x.get('symbol','?'):18s} {x.get('name','')[:52]}")
                    if x.get("symbol"): found.append(x["symbol"])
            except Exception as e: log("     parse:",str(e)[:60],r.text[:150])
    except Exception as e: log(f"  '{q}': {type(e).__name__} {str(e)[:60]}")

log("\n### B. FT chartapi/series dla znalezionych symboli")
cands = list(dict.fromkeys(found))[:8] or []
cands += ["IOM:GAS","IFEU:LF","GASOIL:IOM","LF:IEU","IFEU:GAS"]
for sym in cands:
    try:
        r=requests.post("https://markets.ft.com/data/chartapi/series",timeout=30,
          headers={**H,"Content-Type":"application/json","Referer":"https://markets.ft.com/data/"},
          json={"days":200,"dataNormalized":False,"dataPeriod":"Day","dataInterval":1,
                "realtime":False,"returnDateType":"ISO8601",
                "elements":[{"Label":"g","Type":"price","Symbol":sym,"OverlayIndicators":[],"Params":{}}]})
        ok = r.status_code==200 and '"Status":1' in r.text
        log(f"  {sym:20s} HTTP {r.status_code} {'*** DZIALA ***' if ok else ''} :: {r.text[:170]}")
        if ok:
            d=r.json()
            el=d.get("Elements",[])
            dates=d.get("Dates",[])
            log(f"     dat: {len(dates)}  od {dates[0] if dates else '?'} do {dates[-1] if dates else '?'}")
            if el:
                comp=el[0].get("ComponentSeries",[])
                for c in comp:
                    if c.get("Type")=="Close":
                        v=c.get("Values",[])
                        log(f"     Close: {len(v)} wartosci, ostatnie 5: {v[-5:]}")
    except Exception as e:
        log(f"  {sym:20s} {type(e).__name__}: {str(e)[:60]}")

log("\n### C. portale DE/EU z historia gasoilu")
for n,u in [("onvista search","https://api.onvista.de/api/v1/instruments/search?searchValue=gasoil"),
            ("finanzen.net","https://www.finanzen.net/rohstoffe/gasoelpreis"),
            ("ariva","https://www.ariva.de/gasoil-preis"),
            ("boerse-frankfurt","https://api.boerse-frankfurt.de/v1/search/equity_search?searchTerm=gasoil")]:
    try:
        r=requests.get(u,timeout=30,headers=H)
        log(f"  [{r.status_code}] {n:20s} len={len(r.text):7d} :: {r.text[:180].replace(chr(10),' ')}")
    except Exception as e:
        log(f"  [ERR] {n:20s} {type(e).__name__}: {str(e)[:50]}")
open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
