# Ricerca e backtest — BOT BTC

Script di ricerca del progetto. Importano la libreria condivisa `botbtc/` e leggono le serie storiche da `data/`
(entrambe alla radice del progetto, non qui dentro). Solo libreria standard Python 3.

```bash
# dalla radice del progetto
python3 backtest/backtest_v51.py     # v5.1 (BUY+SELL) vs v4 (solo BUY) vs DCA puro:
                                     # finestre di partenza, eventi SELL, traiettoria annuale
python3 backtest/variants_sell.py    # varianti diagnostiche del modulo SELL (prop / noexp / target / gate)
python3 backtest/validate_mvrv.py    # validazione MVRV + RSI settimanale, 200-WMA, Pi Cycle (vedi docs/02)

# funzionano anche da dentro questa cartella: cd backtest && python3 backtest_v51.py
```

Gli indicatori **non** stanno più qui: sono in `botbtc/indicators.py`, perché sono la libreria che userà anche il bot
live (spostati nella sessione 04; prima erano `backtest/indicators.py`). I percorsi dei dati vengono da `botbtc/paths.py`.

## Dati (`../data/`)

- `btc_close_usd_coinbase.csv` — chiusure giornaliere BTC-USD, Coinbase Exchange, 2017-01-01 → 2026-09-17 (UTC).
  Validazione: 120 candele ri-lette verbatim a campione (tutte identiche); continuità dei timestamp senza buchi.
  Nota: il valore del 2026-09-17 è quello letto il 18-09 sera (candela chiusa).
- `coinmetrics_btc_mvrv.csv` — MVRV (`CapMVRVCur`), market cap (`CapMrktCurUSD`) e prezzo di riferimento (`PriceUSD`)
  giornalieri, CoinMetrics Community API, 2010-07-18 → 2026-09-19 (5.908 righe, 0 buchi, nessuna chiave API).
  Validazione: 9 date sparse ri-lette una per una dall'API (identiche); `PriceUSD` confrontato con le chiusure Coinbase
  su 3.547 giorni (scarto medio 0,18 %, massimo 5,2 %). Ritardo della fonte: il dato del giorno T arriva il giorno T+1.
- `google_trends_bitcoin.csv` — interesse di ricerca per "bitcoin" (Google Trends via pytrends), mensile
  2015→2026, indice 0-100 ricucito su due finestre (100 = dicembre 2017). Si aggiorna con
  `python3 backtest/aggiorna_google_trends.py`, una volta al mese: **il bot legge solo il file**.
- `coinmetrics_basket_mcap.csv` — market cap giornaliere di 13 monete (CoinMetrics community), 2015→2026.
  **Solo ricerca**: serviva a testare la BTC dominance, scartata come indicatore (D36). Il paniere è
  incompleto (mancano SOL, BNB, TRX...), quindi la dominance che se ne ricava non è quella vera.
- `fng_alternative_me.csv` — Fear & Greed giornaliero (alternative.me), 2018-02-01 → 2026-09-18.
  Buchi della fonte: 2018-04-14/15/16, 2024-10-26 (il motore li riempie col valore precedente).
  2018–2021 dalla copia GitHub `edwardchin811227/cryptofear-and-greed-index` (stessa fonte), 2022–2026 dall'API;
  2021 confrontato tra le due copie (identiche dopo correzione di 2 refusi di trascrizione).

Le due serie di prezzi (Coinbase e CoinMetrics) **non vanno mescolate dentro lo stesso calcolo**: vedi `docs/02` §7.

## Interpretazioni della spec (vedi testa di `backtest_v51.py`, I1…I11)

Cambiando la spec (v6) vanno aggiornate lì. Il motore è volutamente "fedele": i bug della spec che non permettevano
l'esecuzione (dip banda 3 = 0, doppio conteggio riserva_dip, 5 lunedì/mese) sono corretti nel modo indicato in
`docs/01_analisi_pseudocodice_v5.1.md` §2.

## Metrica

BTC-equivalente finale = BTC + cash/prezzo_finale, confrontato con il DCA puro a parità di depositi (200/mese, fee 0,1 %).

## Riproducibilità

`validate_mvrv.py` deve riprodurre esattamente `validate_mvrv_output.txt`, che è l'output della corsa della sessione 03
e la fonte dei numeri di `docs/02_indicatori_bot_report.md`. Se un numero del documento non torna, **non fidarti del
documento**: rilancia lo script e confronta.
