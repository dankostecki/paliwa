#!/usr/bin/env python3
"""Diagnostyka zrodel danych — uruchamiana w GitHub Actions (sesja agenta nie ma sieci)."""
import sys, json
from datetime import date, timedelta

OUT = []
def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)

log("=" * 78)
log("PROBE", date.today().isoformat())
log("=" * 78)

# ---------- 1. yfinance ----------
log("\n### yfinance — kandydaci na gasoil + FX")
try:
    import yfinance as yf
    log("yfinance", yf.__version__)
    CANDS = ["LF=F","QS=F","7F=F","G=F","LGO=F","GAS=F","ULS=F","GOIL=F",
             "HO=F","BZ=F","CL=F","RB=F",
             "USDPLN=X","PLN=X"]
    for s in CANDS:
        try:
            h = yf.Ticker(s).history(period="1mo")
            if len(h):
                cur = None
                try: cur = yf.Ticker(s).fast_info.currency
                except Exception: pass
                log(f"  OK   {s:12s} n={len(h):3d} last={h['Close'].iloc[-1]:12.4f} @{h.index[-1].date()} cur={cur}")
            else:
                log(f"  --   {s:12s} pusta seria")
        except Exception as e:
            log(f"  ERR  {s:12s} {type(e).__name__}: {str(e)[:70]}")
except Exception as e:
    log("  yfinance niedostepny:", type(e).__name__, e)

# ---------- 2. stooq ----------
log("\n### stooq — warianty host / endpoint / User-Agent")
import requests
UAS = {
  "chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
  "old":    "Mozilla/5.0",
}
for host in ["stooq.pl", "stooq.com"]:
    for sym in ["lf.f", "cb.f", "usdpln", "plopln3m"]:
        for path, desc in [(f"/q/l/?s={sym}&f=sd2t2ohlcvn&h=&e=json", "json"),
                           (f"/q/d/l/?s={sym}&i=d", "csv")]:
            for uan, ua in UAS.items():
                try:
                    r = requests.get(f"https://{host}{path}", timeout=25,
                                     headers={"User-Agent": ua})
                    head = r.text[:100].replace("\n", "\\n").replace("\r", "")
                    log(f"  {host:10s} {sym:9s} {desc:4s} ua={uan:6s} HTTP {r.status_code} len={len(r.text):6d} :: {head}")
                except Exception as e:
                    log(f"  {host:10s} {sym:9s} {desc:4s} ua={uan:6s} {type(e).__name__}: {str(e)[:50]}")

# ---------- 3. NBP ----------
log("\n### NBP — kurs USD (zapas dla USD/PLN)")
try:
    r = requests.get("https://api.nbp.pl/api/exchangerates/rates/a/usd/last/5/?format=json", timeout=20)
    log(f"  HTTP {r.status_code} :: {r.text[:200]}")
except Exception as e:
    log(f"  {type(e).__name__}: {e}")

# ---------- 4. investing.com ----------
log("\n### investing.com — czy w ogole odpowiada")
for url in ["https://www.investing.com/commodities/london-gas-oil",
            "https://api.investing.com/api/financialdata/8833/historical/chart/?period=P1M&interval=P1D&pointscount=120"]:
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": UAS["chrome"]})
        log(f"  HTTP {r.status_code} len={len(r.text)} {url[:60]} :: {r.text[:120].replace(chr(10),' ')}")
    except Exception as e:
        log(f"  {type(e).__name__}: {str(e)[:60]} {url[:60]}")

open("probe_results.txt", "w", encoding="utf-8").write("\n".join(OUT) + "\n")
log("\nZapisano probe_results.txt")
