# AphroditeBTC

*Love the asset. Analyze the market.*

Bot personale che tiene Bitcoin sotto osservazione e manda su Telegram un **report giornaliero**:
dove si trova il mercato rispetto alle medie e agli indicatori di ciclo, e se è un momento in cui vale
la pena aumentare o ridurre l'acquisto ricorrente (budget di riferimento: 200 €/mese).

Il bot **non compra e non vende**: notifica, l'esecuzione resta a mano.

## Stato

Analisi e indicatori validati; **strato dati del bot funzionante** (fasi F0-F1 del piano): scarica dalle tre fonti
con fallback, tiene un archivio SQLite, controlla la qualità dei dati e calcola tutti gli indicatori del giorno.
Manca il pezzo che decide — il motore *straordinario / normale / freno* (F2) — e Telegram (F4).
Dettagli in [CLAUDE.md](CLAUDE.md) §2 e nel [piano](docs/03_piano_sviluppo.md).

## Struttura

| cartella | contenuto |
|---|---|
| `botbtc/` | libreria condivisa tra backtest e bot: indicatori, fetcher, archivio, controlli |
| `bot/` | livello Telegram: configurazione ed entry point |
| `tests/` | verifiche automatiche delle fasi del piano |
| `data/` | serie storiche scaricate e validate (prezzo, MVRV, Fear & Greed) |
| `backtest/` | script di ricerca: backtest della spec v5.1 e validazione degli indicatori |
| `docs/` | analisi, decisioni, spec sorgente e note di sessione |

## Come si esegue

```bash
python3 bot/main.py --dry-run        # configurazione, senza toccare rete o database
python3 bot/main.py --bootstrap      # crea l'archivio SQLite dai CSV di data/ (senza rete)
python3 bot/main.py --giornaliero    # aggiorna dalle fonti, controlla i dati, stampa la giornata
python3 -m unittest discover -s tests   # le verifiche delle fasi F0-F1
python3 tests/prova_rete.py          # prova reale delle tre fonti (serve rete)

python3 backtest/backtest_v51.py     # v5.1 (BUY+SELL) vs v4 (solo BUY) vs DCA puro
python3 backtest/variants_sell.py    # varianti diagnostiche del modulo SELL
python3 backtest/validate_mvrv.py    # riproduce i numeri di docs/02_indicatori_bot_report.md
```

Serve solo Python 3: la libreria e i backtest non hanno dipendenze e non chiedono chiavi API.
Anche il livello Telegram usa solo la libreria standard (D37): niente da installare, né sul PC né sul VPS.
Messa in esercizio sul VPS: [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

## Documenti

- [`docs/STATO.md`](docs/STATO.md) — **a che punto siamo**: fasi fatte, fasi da fare, decisioni in sospeso
- [`docs/00_decisioni.md`](docs/00_decisioni.md) — tutte le decisioni prese, con la ragione
- [`docs/01_analisi_pseudocodice_v5.1.md`](docs/01_analisi_pseudocodice_v5.1.md) — analisi della spec BUY+SELL e backtest 2018→2026
- [`docs/02_indicatori_bot_report.md`](docs/02_indicatori_bot_report.md) — indicatori del bot di report: MVRV, Mayer, RSI, 200-WMA, Pi Cycle
- [`docs/03_piano_sviluppo.md`](docs/03_piano_sviluppo.md) — il piano a fasi, con le verifiche per sotto-fase
- [`docs/tracking/`](docs/tracking) — cosa è stato fatto, sessione per sessione
