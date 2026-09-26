"""Percorsi del progetto: unica fonte di verita' su dove stanno i dati.

Uso:
    from botbtc.paths import DATA_DIR, PRICES_COINBASE
    from botbtc.paths import DATA          # stringa con separatore finale (DATA + "file.csv")

Gli script dentro backtest/ aggiungono la radice del progetto a sys.path prima
di importare questo modulo, cosi' funzionano sia con `python3 backtest/x.py`
sia con `cd backtest && python3 x.py`.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
DATA = DATA_DIR + os.sep

# I tre file storici scaricati e validati (provenienza e limiti: backtest/README.md)
PRICES_COINBASE = os.path.join(DATA_DIR, "btc_close_usd_coinbase.csv")
FNG_ALTERNATIVE_ME = os.path.join(DATA_DIR, "fng_alternative_me.csv")
MVRV_COINMETRICS = os.path.join(DATA_DIR, "coinmetrics_btc_mvrv.csv")

# Database del bot: cache delle fonti e archivio storico (F1.2).
# Si puo' spostare fuori dal codice con la variabile d'ambiente BOTBTC_DB
# (sul VPS la cartella dati sta fuori dal repository, vedi piano F5.1).
DB_DEFAULT = os.environ.get("BOTBTC_DB") or os.path.join(DATA_DIR, "botbtc.sqlite3")
