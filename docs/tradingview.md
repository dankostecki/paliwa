# Jak pobieramy notowania ICE Gasoil z TradingView

Dokument opisuje `tradingview_history()` w [`lib_fetch.py`](../lib_fetch.py) — funkcję, która
zasila `data/ice_history.json`. Metoda jest nieoczywista, więc warto mieć w repo wyjaśnienie
**co** kod robi, **dlaczego akurat tak**, i **co już sprawdzono i odpadło**.

Stan na 2026-09-10.

---

## 1. Co pobieramy

| | |
|---|---|
| Symbol | `ICEEUR:ULS1!` — „Low Sulphur Gasoil Futures", kontrakt ciągły (front month) |
| Giełda | ICE Futures Europe |
| Wartość | dzienny `close` |
| Jednostka | USD za tonę metryczną |
| Krok notowań | $0,25 (przydatne do walidacji, patrz §7) |

W `fetch_ice.py` symbol jest rozbity na dwie stałe, bo protokół oczekuje ich osobno:

```python
TV_GASOIL_EXCHANGE = "ICEEUR"
TV_GASOIL_TICKER   = "ULS1!"
GASOIL_MIN, GASOIL_MAX = 300.0, 3000.0   # USD/tonę — pasmo wiarygodności
```

Wynik trafia do wzoru (`DENSITY = 0.845` kg/l, gęstość kontraktowa wg specyfikacji ICE):

```
ICE [USD/tonę] × 0,845 × USD/PLN = ICE [PLN/1000 l]
```

Kurs USD/PLN pochodzi z osobnego źródła (yfinance `USDPLN=X`, zapasowo API NBP) i jest łączony
z gasoilem **po dacie**, nie po kolejności.

---

## 2. Dlaczego WebSocket, a nie zwykły REST

TradingView ma publiczny endpoint REST:

```
GET https://scanner.tradingview.com/symbol?symbol=ICEEUR:ULS1!&fields=close,open,high,low
→ {"close":1391.25,"open":1400.25,"high":1403.5,"low":1368.5}
```

…ale to **migawka bieżąca, bez dat i bez historii**. Zostaje w kodzie jako ostatni fallback
(`tradingview_quote()`), przydatny tylko do dopisania dnia bieżącego.

Historię trzeba wziąć protokołem WebSocket, którym karmią się same wykresy TradingView.

### Co sprawdzono i odpadło

| Źródło | Wynik |
|---|---|
| Yahoo Finance / yfinance | **brak kontraktu** — wyszukiwarka symboli na „gasoil" zwraca wyłącznie indeksy S&P GSCI; `LF=F`, `QS=F`, `7F=F`, `G=F`, `LGO=F` oraz datowane NYMEX → 404 |
| stooq | zapora anty-botowa od 2026-06-04 (JS proof-of-work + `/__verify`) |
| investing.com | 403 na stronie i na `tvc4`/`tvc6` |
| theice.com `DelayedMarkets` | 403 (productguide działa, ale bez cen) |
| Nasdaq Data Link (`CHRIS/ICE_G1`) | 403 |
| FT markets | tylko ETC-y i indeksy UBS/GSCI, nie sam kontrakt |
| onvista | tylko indeksy S&P GSCI |
| Barchart / WSJ / MarketWatch | 403 / captcha / 401 |
| EIA, Alpha Vantage | wymagają klucza API |

Historyczne endpointy samego TradingView poza WebSocketem też nie działają:
`history.tradingview.com` i `udf.tradingview.com` się nie rozwiązują, `demo-feed-data`
zwraca puste tablice, `symbol-search` daje 403.

---

## 3. Protokół krok po kroku

Jedyna zależność to `websocket-client` (w `update_ice.yml`: `pip install requests yfinance websocket-client`).

### Połączenie

```python
ws = create_connection(
    "wss://data.tradingview.com/socket.io/websocket?from=chart%2F",
    header=["User-Agent: Mozilla/5.0"],
    origin="https://www.tradingview.com", timeout=30)
```

Nagłówek `Origin` jest istotny — bez niego serwer zrywa połączenie.

### Format ramki

Każda wiadomość jest poprzedzona własną długością:

```
~m~<liczba znaków JSON-a>~m~<JSON>
```

```python
def _frame(method, params):
    body = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(body)}~m~{body}"
```

`separators` bez spacji ma znaczenie: długość w prefiksie musi zgadzać się co do znaku.

### Sekwencja startowa

Identyfikator sesji to losowy ciąg — `_sess("cs")` daje np. `cs_qwertyuiopas`:

```python
cs = _sess("cs")   # prefiks + "_" + 12 losowych małych liter

("set_auth_token",       ["unauthorized_user_token"])
("chart_create_session", [cs, ""])
("resolve_symbol",       [cs, "sds_sym_1",
                          '={"symbol":"ICEEUR:ULS1!","adjustment":"splits"}'])
("create_series",        [cs, "sds_1", "s1", "sds_sym_1", "1D", 400, ""])
```

- `unauthorized_user_token` — dostęp anonimowy, bez konta. Działa dla tego instrumentu.
- `"1D"` — interwał dzienny.
- `400` — liczba słupków wstecz, parametr `n_bars` funkcji `tradingview_history()`
  (domyślnie `n_bars=400`, ok. 19 miesięcy sesyjnych). Filtrowanie po dacie robimy
  potem, lokalnie.

### Pętla odbioru

```python
deadline = time.time() + 45
while time.time() < deadline:
    chunk = ws.recv()
    raw += chunk
    if "series_completed" in raw:
        break
    for ping in re.findall(r"~m~\d+~m~(~h~\d+)", chunk):
        ws.send(f"~m~{len(ping)}~m~{ping}")
```

Serwer wysyła heartbeaty `~h~N` i **oczekuje ich odbicia** — bez tego rozłącza. Sygnałem
kompletu danych jest `series_completed`; brak tego znacznika jest logowany jako ostrzeżenie.

---

## 4. Parsowanie odpowiedzi

Dane siedzą w wiadomościach `du`/`timescale_update`. Wyciągamy je dwoma wyrażeniami:

```python
for blob in re.findall(r'"s":\[(.*?)\],"ns"', raw, re.S):
    for m in re.finditer(r'\{"i":\d+,"v":\[([0-9eE\.\+\-,]+)\]\}', blob):
        v = [float(x) for x in m.group(1).split(",")]
```

Wektor `v` to:

```
[0] timestamp (epoch, sekundy)   [1] open   [2] high
[3] low                          [4] close  [5] volume
```

Bierzemy `v[4]`.

---

## 5. Pułapka datowania — najważniejsza rzecz w tym pliku

**ICE otwiera sesję poniedziałkową w niedzielę o 22:00, a TradingView znakuje słupki czasem
OTWARCIA.** Bez korekty cały poniedziałek ląduje pod niedzielą.

Rozkład dni tygodnia w surowej serii 300 słupków:

```
pon=0   wt=61  śr=61  czw=59  pt=59  sob=0  NDZ=60      ← źle
```

Po korekcie:

```
pon=60  wt=61  śr=61  czw=59  pt=59  sob=0  NDZ=0       ← dobrze
```

```python
ts = datetime.fromtimestamp(v[0], tz=timezone.utc)
d = ts.date()
if ts.weekday() == 6:          # niedziela 22:00 = otwarcie poniedziałku
    d = d + timedelta(days=1)
```

To **nie jest** zwykłe przesunięcie całej serii — dotyczy wyłącznie słupków otwartych
w niedzielę. Sprawdzone: globalne offsety −1 i +1 dnia wypadały wyraźnie gorzej wobec
danych referencyjnych (średni błąd 3,79% i 3,15% wobec 1,04% przy offsecie 0).

---

## 6. Walidacja w kodzie

- **Pasmo** `GASOIL_MIN..GASOIL_MAX` (300–3000 USD/t) — chroni przed cichym wzięciem
  instrumentu w złej jednostce. Słupki spoza pasma są pomijane i zliczane w logu.
- **Filtr daty** — słupki starsze niż `start` są odrzucane.
- **Kontrakt zwracanej wartości** — `{"RRRR-MM-DD": close}`, dokładnie ten sam co
  `yf_series()` i `stooq_csv_series()`. Dzięki temu `main()` nie traktuje tego źródła
  wyjątkowo i cała logika łączenia po dacie działa bez zmian.
- **Błąd** — `log.warning` i pusty słownik. Nigdy wyjątek w górę; o tym, czy brak danych jest
  problemem, decyduje `main()` przez `STALE_AFTER_DAYS`.

---

## 7. Jak zweryfikowano poprawność

Dwa niezależne testy, oba przeszły:

**Porównanie z danymi referencyjnymi.** Archiwum za 2026-01-09 … 2026-03-05 pochodzi z arkusza
Google autora (import pierwotny). Wobec niego seria z TradingView:

- **38/40** wartości identycznych co do grosza
- **40/40** w tolerancji 0,5%
- średni błąd **0,02%**

**Test kroku notowań.** ICE Gasoil kwotuje się w krokach $0,25, więc każda prawdziwa cena musi
być wielokrotnością ćwiartki:

| Źródło | Wielokrotności $0,25 |
|---|---|
| TradingView | **300/300** |
| stooq (blok 2026-03-06 … 06-04) | **27/64** |

Wartości typu `1076.37`, `1128.24`, `1019.87` nie mogą być cenami tego kontraktu. To był
dowód, że stooq podawał coś innego — i powód, dla którego te 64 wpisy zostały podmienione
(PR #29).

---

## 8. Dlaczego nie biblioteka `tvdatafeed`

Istnieje gotowa biblioteka robiąca to samo:

```python
from tvDatafeed import TvDatafeed, Interval
TvDatafeed().get_hist(symbol="ULS1!", exchange="ICEEUR",
                      interval=Interval.in_daily, n_bars=300)
```

Sprawdzona — daje **dokładnie te same liczby**. Odrzucona, bo `pip install tvdatafeed` nie
przechodzi z PyPI (pierwszy przebieg workflow padł właśnie na tym kroku), a instalacja
z gita w produkcyjnym workflow to zbędne ryzyko łańcucha dostaw. Surowy WebSocket wymaga
jednej zależności z PyPI i kilkudziesięciu linii kodu, które kontrolujemy.

---

## 9. Gdy to przestanie działać

Protokół jest wewnętrzny i niestabilny — może się zmienić bez zapowiedzi. Zabezpieczenia:

1. **Łańcuch zapasowy** w `get_gasoil()`: TradingView (historia) → Yahoo → stooq → scanner TV.
   Yahoo i stooq zostają, gdyby kiedyś wróciły.
2. **Głośna awaria** — gdy żadne źródło nie odpowie, a ostatni wpis jest starszy niż
   `STALE_AFTER_DAYS` (7 dni), `fetch_ice.py` kończy się kodem 1 i workflow robi się czerwony.
   Poprzednia wersja miała tu ciche `return`, przez co archiwum stało trzy miesiące
   niezauważone.
3. **Diagnostyka** — log wypisuje liczbę odebranych znaków i brak `series_completed`,
   co pozwala odróżnić zerwane połączenie od zmiany formatu.

### Przydatne przełączniki

```bash
python fetch_ice.py                              # normalny przebieg (tak woła cron)
python fetch_ice.py --refresh-from 2026-03-06    # świadoma podmiana zakresu wstecz
```

`--refresh-from` nadpisuje istniejące wpisy od podanej daty, ale koryguje **wyłącznie**
`ice_usd_tonne` i przelicza `ice_pln_1000l` — zapisany kurs USD/PLN zostaje nietknięty
(dwa źródła FX różnią się momentem snapshotu, nie poprawnością).

Bez tego argumentu automatycznemu odświeżeniu podlega tylko okno `BACKFILL_LOOKBACK_DAYS = 21`
dni, żeby cron nie przepisywał historii po cichu. To okno istnieje po to, by wartość złapana
w trakcie sesji skorygowała się później do zamknięcia.

---

## 10. Zastrzeżenie

To wewnętrzne API TradingView, a regulamin serwisu zabrania automatycznego pobierania danych;
notowania ICE są danymi licencjonowanymi. Wybór został podjęty świadomie przez właściciela
projektu po przedstawieniu tego zastrzeżenia i po tym, jak wszystkie alternatywy z §2 okazały
się niedostępne.
