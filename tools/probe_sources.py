#!/usr/bin/env python3
"""Runda 7: onvista — od wyszukiwarki do historii dziennej gasoilu."""
from datetime import date
import requests, json
OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
H={"User-Agent":UA,"Accept":"application/json"}
log("="*78); log("PROBE runda 7 — onvista —", date.today().isoformat()); log("="*78)

log("\n### A. onvista search — pelna odpowiedz")
cands=[]
for q in ["gasoil","gasöl","low sulphur"]:
    try:
        r=requests.get("https://api.onvista.de/api/v1/instruments/search",
                       params={"searchValue":q},timeout=30,headers=H)
        log(f"  '{q}': HTTP {r.status_code}")
        if r.status_code==200:
            for it in r.json().get("list",[])[:12]:
                log("     type=%-10s entity=%-12s id=%-12s %s" % (
                    it.get("type"), it.get("entityType"), it.get("entityValue"),
                    (it.get("name") or "")[:50]))
                cands.append((it.get("entityType"), it.get("entityValue"), it.get("name")))
    except Exception as e: log(f"  '{q}': {type(e).__name__} {str(e)[:60]}")

log("\n### B. szczegoly instrumentow (szukamy tego w USD/tone, ~1394)")
seen=set()
for et,eid,name in cands:
    if not eid or eid in seen: continue
    seen.add(eid)
    for path in [f"https://api.onvista.de/api/v1/instruments/{et}/{eid}/snapshot",
                 f"https://api.onvista.de/api/v1/instruments/{eid}/snapshot"]:
        try:
            r=requests.get(path,timeout=25,headers=H)
            if r.status_code==200:
                d=r.json()
                q=d.get("quote") or {}
                inst=d.get("instrument") or {}
                log(f"  OK {et}/{eid} {str(name)[:34]:34s} last={q.get('last')} cur={q.get('isoCurrency')} idNot={q.get('idNotation')}")
                break
            else:
                log(f"  [{r.status_code}] {path[-58:]}")
        except Exception as e:
            log(f"  ERR {type(e).__name__} {path[-50:]}")

log("\n### C. proba historii dziennej dla kazdego kandydata")
for et,eid,name in cands:
    if not eid: continue
    for tmpl in [f"https://api.onvista.de/api/v1/instruments/{et}/{eid}/eod_history?range=Y1",
                 f"https://api.onvista.de/api/v1/instruments/{et}/{eid}/chart_history?range=Y1"]:
        try:
            r=requests.get(tmpl,timeout=25,headers=H)
            if r.status_code==200 and len(r.text)>200:
                log(f"  *** {et}/{eid} {str(name)[:30]} :: {r.text[:260]}")
            else:
                log(f"  [{r.status_code}] len={len(r.text):6d} {et}/{eid}")
        except Exception as e:
            log(f"  ERR {type(e).__name__} {et}/{eid}")

log("\n### D. kontrola: TradingView scanner (dziala, ale tylko biezace)")
try:
    r=requests.get("https://scanner.tradingview.com/symbol",
        params={"symbol":"ICEEUR:ULS1!","fields":"close,open,high,low,description,update_mode","no_404":"true"},
        timeout=25,headers=H)
    log(f"  TV: {r.status_code} :: {r.text[:200]}")
except Exception as e: log("  TV err",e)

open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
