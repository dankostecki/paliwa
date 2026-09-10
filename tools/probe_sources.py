#!/usr/bin/env python3
"""Sonda: czy anonimowy dostep do TradingView zwraca DZIENNE SLUPKI dla ICEEUR:ULS1!"""
import json, random, re, string, sys, time
from datetime import date, datetime, timezone

OUT=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); OUT.append(s)

# Kotwice: dwie niezaleznie zdobyte prawdziwe wartosci do weryfikacji serii
ANCHORS={"2026-06-04":1076.37, "2026-09-10":1391.25}
log("="*78); log("SONDA TradingView — historia ICEEUR:ULS1! —", date.today().isoformat())
log("kotwice do sprawdzenia:", ANCHORS); log("="*78)

def check(series, name):
    """Porownuje serie z kotwicami. series = {data: close}"""
    log(f"\n  --- kontrola kotwic dla: {name} ---")
    if not series:
        log("     brak serii"); return False
    ds=sorted(series)
    log(f"     slupkow: {len(ds)}, zakres {ds[0]} .. {ds[-1]}")
    ok=True
    for d,expect in ANCHORS.items():
        got=series.get(d)
        if got is None:
            log(f"     {d}: BRAK w serii (oczekiwano {expect})"); ok=False
        else:
            diff=abs(got-expect)/expect*100
            verdict="OK" if diff<=0.5 else "ROZJAZD"
            log(f"     {d}: {got} vs {expect} -> {diff:.3f}% [{verdict}]")
            if diff>0.5: ok=False
    log(f"     ostatnie 5: {[(d,series[d]) for d in ds[-5:]]}")
    return ok

# ---------- DROGA 1: tvdatafeed ----------
log("\n### DROGA 1: biblioteka tvdatafeed")
try:
    from tvDatafeed import TvDatafeed, Interval
    log("  import OK")
    try:
        tv=TvDatafeed()
        df=tv.get_hist(symbol="ULS1!",exchange="ICEEUR",interval=Interval.in_daily,n_bars=250)
        if df is None or len(df)==0:
            log("  get_hist zwrocil pusto")
        else:
            log(f"  get_hist: {len(df)} wierszy, kolumny={list(df.columns)}")
            s={idx.date().isoformat():float(r["close"]) for idx,r in df.iterrows()}
            check(s,"tvdatafeed ULS1!")
    except Exception as e:
        log(f"  get_hist blad: {type(e).__name__}: {str(e)[:150]}")
except ImportError as e:
    log(f"  brak biblioteki: {e}")
except Exception as e:
    log(f"  blad: {type(e).__name__}: {str(e)[:120]}")

# ---------- DROGA 2: surowy WebSocket ----------
log("\n### DROGA 2: surowy WebSocket data.tradingview.com")
try:
    from websocket import create_connection
    def sess(p): return p+"_"+"".join(random.choice(string.ascii_lowercase) for _ in range(12))
    def msg(m,p):
        body=json.dumps({"m":m,"p":p},separators=(",",":"))
        return f"~m~{len(body)}~m~{body}"
    ws=create_connection("wss://data.tradingview.com/socket.io/websocket?from=chart%2F",
        header=["User-Agent: Mozilla/5.0"], origin="https://www.tradingview.com", timeout=25)
    cs=sess("cs"); qs=sess("qs")
    for m,p in [("set_auth_token",["unauthorized_user_token"]),
                ("chart_create_session",[cs,""]),
                ("quote_create_session",[qs]),
                ("resolve_symbol",[cs,"sds_sym_1",
                    '={"symbol":"ICEEUR:ULS1!","adjustment":"splits"}']),
                ("create_series",[cs,"sds_1","s1","sds_sym_1","1D",300,""])]:
        ws.send(msg(m,p))
    raw=""; t0=time.time()
    while time.time()-t0 < 45:
        try: chunk=ws.recv()
        except Exception: break
        raw+=chunk
        if "series_completed" in raw: break
        for h in re.findall(r"~m~(\d+)~m~~h~\d+", chunk):
            pass
        for ping in re.findall(r"~m~\d+~m~(~h~\d+)", chunk):
            ws.send(f"~m~{len(ping)}~m~{ping}")
    ws.close()
    log(f"  odebrano {len(raw)} znakow, series_completed={'series_completed' in raw}")
    bars={}
    for blob in re.findall(r'"s":\[(.*?)\],"ns"', raw, re.S):
        for m in re.finditer(r'\{"i":\d+,"v":\[([0-9eE\.\+\-,]+)\]\}', blob):
            v=[float(x) for x in m.group(1).split(",")]
            if len(v)>=5:
                d=datetime.fromtimestamp(v[0],tz=timezone.utc).date().isoformat()
                bars[d]=v[4]
    log(f"  sparsowano slupkow: {len(bars)}")
    check(bars,"raw websocket")
    if not bars and raw:
        log("  PROBKA: "+raw[:400].replace("\n"," "))
except ImportError:
    log("  brak websocket-client")
except Exception as e:
    log(f"  blad: {type(e).__name__}: {str(e)[:150]}")

open("probe_results.txt","w",encoding="utf-8").write("\n".join(OUT)+"\n")
