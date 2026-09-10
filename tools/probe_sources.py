#!/usr/bin/env python3
"""Sonda 2: ustalic POPRAWNE mapowanie dat slupkow TV na daty sesji."""
import json, random, re, string, time
from datetime import date, datetime, timezone, timedelta
OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)
log("="*78); log("SONDA 2 — mapowanie dat"); log("="*78)

# archiwum ze stooq: 104 wpisy 2026-01-09..2026-06-04 = wzorzec odniesienia
ref={e["date"]:e["ice_usd_tonne"] for e in json.load(open("data/ice_history.json"))}
log(f"wzorzec (archiwum): {len(ref)} wpisow, {min(ref)} .. {max(ref)}")

from tvDatafeed import TvDatafeed, Interval
tv=TvDatafeed()
df=tv.get_hist(symbol="ULS1!",exchange="ICEEUR",interval=Interval.in_daily,n_bars=300)
log(f"TV: {len(df)} slupkow")

log("\n### surowe znaczniki czasu — ostatnie 12 slupkow")
for idx,r in list(df.iterrows())[-12:]:
    log(f"  index={idx}  (typ {type(idx).__name__})  weekday={idx.weekday()}  close={r['close']}")

log("\n### rozklad dni tygodnia w calej serii")
from collections import Counter
c=Counter(idx.weekday() for idx,_ in df.iterrows())
names=["pon","wt","sr","czw","pt","SOB","NDZ"]
log("  "+"  ".join(f"{names[k]}={c.get(k,0)}" for k in range(7)))

log("\n### dopasowanie do archiwum przy przesunieciu -1 / 0 / +1 dnia")
best=None
for off in (-1,0,1):
    s={}
    for idx,r in df.iterrows():
        d=(idx.date()+timedelta(days=off)).isoformat()
        s[d]=float(r["close"])
    common=sorted(set(s)&set(ref))
    if not common:
        log(f"  offset {off:+d}: brak pokrycia"); continue
    diffs=[abs(s[d]-ref[d])/ref[d]*100 for d in common]
    avg=sum(diffs)/len(diffs)
    within=sum(1 for x in diffs if x<=0.5)
    log(f"  offset {off:+d}: pokrycie {len(common):3d} dni, sredni blad {avg:6.3f}%, "
        f"w tolerancji 0.5%: {within}/{len(common)}")
    if best is None or avg<best[1]: best=(off,avg,len(common),within)

log(f"\n  NAJLEPSZE: offset {best[0]:+d} (sredni blad {best[1]:.3f}%, {best[3]}/{best[2]} w tolerancji)")

off=best[0]
s={(idx.date()+timedelta(days=off)).isoformat():float(r["close"]) for idx,r in df.iterrows()}
log(f"\n### po korekcie offset {off:+d} — rozklad dni tygodnia")
c2=Counter(datetime.strptime(d,"%Y-%m-%d").weekday() for d in s)
log("  "+"  ".join(f"{names[k]}={c2.get(k,0)}" for k in range(7)))

log("\n### 12 najwiekszych rozbieznosci wobec archiwum (offset %+d)"%off)
common=sorted(set(s)&set(ref))
rows=sorted(((abs(s[d]-ref[d])/ref[d]*100,d,s[d],ref[d]) for d in common),reverse=True)
for e,d,a,b in rows[:12]:
    log(f"  {d}  TV={a:9.2f}  archiwum={b:9.2f}  {e:6.3f}%")

log("\n### co wpadnie w luke 2026-06-05..2026-09-09 (offset %+d)"%off)
gap=sorted(d for d in s if "2026-06-05"<=d<="2026-09-09")
log(f"  slupkow do dopisania: {len(gap)}")
log(f"  pierwsze 5: {[(d,s[d]) for d in gap[:5]]}")
log(f"  ostatnie 5: {[(d,s[d]) for d in gap[-5:]]}")
wd=Counter(datetime.strptime(d,"%Y-%m-%d").weekday() for d in gap)
log("  dni tygodnia w luce: "+"  ".join(f"{names[k]}={wd.get(k,0)}" for k in range(7)))
open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
