#!/usr/bin/env python3
"""Sonda 3: poprawne datowanie (ndz 22:00 -> pon) + ktory symbol pasuje do archiwum."""
import json
from collections import Counter
from datetime import datetime, timedelta
OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
log("="*78); log("SONDA 3 — datowanie i zgodnosc serii"); log("="*78)

ref={e["date"]:e["ice_usd_tonne"] for e in json.load(open("data/ice_history.json"))}
log(f"archiwum: {len(ref)} wpisow {min(ref)}..{max(ref)}")

# czy wartosci archiwum sa wielokrotnosciami ticku 0.25?
def tick_ok(v): return abs(round(v*4)-v*4) < 1e-6
n_tick=sum(1 for v in ref.values() if tick_ok(v))
log(f"archiwum: {n_tick}/{len(ref)} wartosci to wielokrotnosc ticku 0.25 ICE")
log(f"  przyklady nie-tickowe: {[v for v in list(ref.values()) if not tick_ok(v)][:8]}")

from tvDatafeed import TvDatafeed, Interval
tv=TvDatafeed()

def norm(idx):
    """Slupek otwarty w niedziele 22:00 nalezy do poniedzialku."""
    d=idx.date()
    if idx.weekday()==6:      # niedziela
        d=d+timedelta(days=1)
    return d.isoformat()

names=["pon","wt","sr","czw","pt","SOB","NDZ"]
for sym in ["ULS1!","ULS2!","ULS3!"]:
    log(f"\n### {sym}")
    try:
        df=tv.get_hist(symbol=sym,exchange="ICEEUR",interval=Interval.in_daily,n_bars=300)
    except Exception as e:
        log(f"  blad: {type(e).__name__}: {str(e)[:80]}"); continue
    if df is None or not len(df):
        log("  brak danych"); continue
    s={norm(idx):float(r["close"]) for idx,r in df.iterrows()}
    c=Counter(datetime.strptime(d,"%Y-%m-%d").weekday() for d in s)
    log(f"  slupkow {len(s)}, dni tygodnia: "+"  ".join(f"{names[k]}={c.get(k,0)}" for k in range(7)))
    n_t=sum(1 for v in s.values() if tick_ok(v))
    log(f"  wielokrotnosc ticku 0.25: {n_t}/{len(s)}")
    common=sorted(set(s)&set(ref))
    if not common: log("  brak pokrycia"); continue
    diffs=[abs(s[d]-ref[d])/ref[d]*100 for d in common]
    avg=sum(diffs)/len(diffs); mx=max(diffs)
    within=sum(1 for x in diffs if x<=0.5)
    med=sorted(diffs)[len(diffs)//2]
    log(f"  pokrycie {len(common)} dni | sredni blad {avg:.3f}% | mediana {med:.3f}% "
        f"| max {mx:.3f}% | w tol. 0.5%: {within}/{len(common)}")

log("\n### wniosek dla ULS1! po poprawnym datowaniu — najgorsze dni")
df=tv.get_hist(symbol="ULS1!",exchange="ICEEUR",interval=Interval.in_daily,n_bars=300)
s={norm(idx):float(r["close"]) for idx,r in df.iterrows()}
common=sorted(set(s)&set(ref))
rows=sorted(((abs(s[d]-ref[d])/ref[d]*100,d,s[d],ref[d]) for d in common),reverse=True)
for e,d,a,b in rows[:10]:
    log(f"  {d} ({names[datetime.strptime(d,'%Y-%m-%d').weekday()]})  TV={a:9.2f}  arch={b:9.2f}  {e:6.3f}%")
log("\n  najlepsze 5:")
for e,d,a,b in rows[-5:]:
    log(f"  {d}  TV={a:9.2f}  arch={b:9.2f}  {e:6.3f}%")

log(f"\n### luka 2026-06-05..2026-09-09 po poprawnym datowaniu")
gap=sorted(d for d in s if "2026-06-05"<=d<="2026-09-09")
c=Counter(datetime.strptime(d,"%Y-%m-%d").weekday() for d in gap)
log(f"  slupkow: {len(gap)} | "+"  ".join(f"{names[k]}={c.get(k,0)}" for k in range(7)))
open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
