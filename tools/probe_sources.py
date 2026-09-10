#!/usr/bin/env python3
"""Sonda 4: czy rozjazd siedzi w danych ze stooq, a arkusz zgadza sie z TV co do grosza?"""
import json
from datetime import timedelta
OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
log("="*78); log("SONDA 4 — ktore zrodlo archiwum jest wiarygodne"); log("="*78)

ref={e["date"]:e["ice_usd_tonne"] for e in json.load(open("data/ice_history.json"))}
from tvDatafeed import TvDatafeed, Interval
tv=TvDatafeed()
df=tv.get_hist(symbol="ULS1!",exchange="ICEEUR",interval=Interval.in_daily,n_bars=300)
def norm(idx):
    d=idx.date()
    return (d+timedelta(days=1)).isoformat() if idx.weekday()==6 else d.isoformat()
s={norm(i):float(r["close"]) for i,r in df.iterrows()}

# Arkusz Google pokrywal 2026-01-09..2026-03-05 (import poczatkowy).
# Pozniej dane dokladal stooq.
SHEET_END="2026-03-05"
def tick(v): return abs(round(v*4)-v*4)<1e-6

for label,sel in [("ARKUSZ (<= %s)"%SHEET_END, lambda d: d<=SHEET_END),
                  ("STOOQ  (>  %s)"%SHEET_END, lambda d: d>SHEET_END)]:
    common=sorted(d for d in set(s)&set(ref) if sel(d))
    if not common: log(f"\n### {label}: brak pokrycia"); continue
    diffs=[abs(s[d]-ref[d])/ref[d]*100 for d in common]
    exact=sum(1 for d in common if abs(s[d]-ref[d])<1e-9)
    within=sum(1 for x in diffs if x<=0.5)
    ticks=sum(1 for d in common if tick(ref[d]))
    log(f"\n### {label}")
    log(f"  dni: {len(common)}  ({common[0]} .. {common[-1]})")
    log(f"  IDENTYCZNE co do grosza: {exact}/{len(common)}")
    log(f"  w tolerancji 0.5%:       {within}/{len(common)}")
    log(f"  sredni blad:             {sum(diffs)/len(diffs):.4f}%")
    log(f"  max blad:                {max(diffs):.3f}%")
    log(f"  archiwum tickowe (0.25): {ticks}/{len(common)}")

log("\n### wniosek")
c_all=sorted(set(s)&set(ref))
sheet=[d for d in c_all if d<=SHEET_END]
stooq=[d for d in c_all if d>SHEET_END]
ex_sheet=sum(1 for d in sheet if abs(s[d]-ref[d])<1e-9)
ex_stooq=sum(1 for d in stooq if abs(s[d]-ref[d])<1e-9)
log(f"  arkusz: {ex_sheet}/{len(sheet)} identycznych z TradingView")
log(f"  stooq:  {ex_stooq}/{len(stooq)} identycznych z TradingView")
if len(sheet) and ex_sheet/len(sheet)>0.9 and (not len(stooq) or ex_stooq/max(len(stooq),1)<0.5):
    log("  => TradingView odtwarza dane z arkusza uzytkownika co do grosza.")
    log("     Rozjazd dotyczy WYLACZNIE okresu, ktory dokladal stooq.")
open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
