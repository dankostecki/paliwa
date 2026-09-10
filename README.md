# paliwa

Dashboard hurtowych cen paliw Orlen zestawionych z parytetem ICE Gasoil.

## Źródła danych

| Dane | Plik | Skrypt | Źródło |
|---|---|---|---|
| Ceny hurtowe Orlen (PB95, Ekodiesel) | `*_2022-2026.json` / `.csv` | `orlen_scraper.py` | orlen.pl (Playwright), zapasowo cenypaliw.fyi |
| ICE Low Sulphur Gasoil + USD/PLN | `data/ice_history.json` | `fetch_ice.py` | TradingView `ICEEUR:ULS1!`, kurs z yfinance |
| Stopy NBP | `data/nbp_history.json` | `fetch_nbp.py` | static.nbp.pl |
| Kontrakty FRA | `data/fra_history.json` | `fetch_fra.py` | scraping |
| WIBOR 3M | `data/wibor_history.json` | `fetch_wibor.py` | **nieaktywne** — stooq postawił zaporę anty-botową, harmonogram wyłączony |

## Dokumentacja

- [**Jak pobieramy notowania ICE Gasoil z TradingView**](docs/tradingview.md) — protokół
  WebSocket, pułapka datowania sesji, walidacja i co robić, gdy przestanie działać.
