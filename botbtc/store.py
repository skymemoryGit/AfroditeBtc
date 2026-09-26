"""Cache e archivio storico in SQLite (F1.2 del piano).

Il database e' insieme la cache delle fonti e la memoria del bot: si inizializza una volta
dai CSV gia' validati in `data/`, poi ogni giorno aggiunge solo i giorni che mancano.

Principi:
- **una riga per giorno per fonte**, chiave primaria sulla data: riscrivere lo stesso giorno
  e' innocuo (idempotente), quindi un'esecuzione doppia non sporca niente;
- **si tiene traccia della fonte** di ogni riga: se un giorno arriva dal fallback Binance
  invece che da Coinbase, resta scritto e il bot lo puo' dire;
- **nessuna rete qui dentro** se non attraverso `aggiorna_da_rete`, che chiama i fetcher e
  **non solleva eccezioni**: restituisce un rapporto con cosa e' andato storto, perche' il
  bot deve poter parlare lo stesso con i dati che ha (F2.6).
"""

import csv
import datetime
import os
import sqlite3

from . import fetchers
from .paths import DB_DEFAULT, FNG_ALTERNATIVE_ME, MVRV_COINMETRICS, PRICES_COINBASE

SCHEMA_VERSIONE = "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prezzi (
    data TEXT PRIMARY KEY,
    chiusura REAL NOT NULL,
    fonte TEXT NOT NULL,
    aggiornato_il TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mvrv (
    data TEXT PRIMARY KEY,
    mvrv REAL NOT NULL,
    market_cap REAL NOT NULL,
    price_usd REAL NOT NULL,
    fonte TEXT NOT NULL,
    aggiornato_il TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fng (
    data TEXT PRIMARY KEY,
    valore INTEGER NOT NULL,
    fonte TEXT NOT NULL,
    aggiornato_il TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS registro (
    data TEXT PRIMARY KEY,
    stato TEXT NOT NULL,
    punteggio_economico REAL,
    punteggio_caro REAL,
    moltiplicatore REAL,
    prezzo REAL,
    indicatori TEXT,
    messaggio TEXT,
    inviato INTEGER NOT NULL DEFAULT 0,
    esito TEXT,
    scritto_il TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS impostazioni (
    chiave TEXT PRIMARY KEY,
    valore TEXT NOT NULL,
    aggiornato_il TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    chiave TEXT PRIMARY KEY,
    valore TEXT NOT NULL
);
"""

TABELLE = ("prezzi", "mvrv", "fng")


def _ora():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def apri(percorso=None):
    """Apre (creando se serve) il database e garantisce lo schema."""
    percorso = percorso or DB_DEFAULT
    cartella = os.path.dirname(os.path.abspath(percorso))
    if cartella:
        os.makedirs(cartella, exist_ok=True)
    conn = sqlite3.connect(percorso)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(chiave, valore) VALUES ('schema', ?)", (SCHEMA_VERSIONE,))
    conn.commit()
    return conn

# ------------------------------------------------------------- scrittura

def upsert_prezzi(conn, righe, fonte):
    """righe: iterabile di (date, chiusura). Ritorna il numero di righe scritte."""
    ora = _ora()
    dati = [(g.isoformat(), float(c), fonte, ora) for g, c in righe]
    conn.executemany("INSERT INTO prezzi(data, chiusura, fonte, aggiornato_il) VALUES (?,?,?,?) "
                     "ON CONFLICT(data) DO UPDATE SET chiusura=excluded.chiusura, "
                     "fonte=excluded.fonte, aggiornato_il=excluded.aggiornato_il", dati)
    conn.commit()
    return len(dati)


def upsert_mvrv(conn, righe, fonte="coinmetrics"):
    """righe: iterabile di (date, mvrv, market_cap, price_usd)."""
    ora = _ora()
    dati = [(g.isoformat(), float(m), float(mc), float(p), fonte, ora) for g, m, mc, p in righe]
    conn.executemany("INSERT INTO mvrv(data, mvrv, market_cap, price_usd, fonte, aggiornato_il) "
                     "VALUES (?,?,?,?,?,?) ON CONFLICT(data) DO UPDATE SET mvrv=excluded.mvrv, "
                     "market_cap=excluded.market_cap, price_usd=excluded.price_usd, "
                     "fonte=excluded.fonte, aggiornato_il=excluded.aggiornato_il", dati)
    conn.commit()
    return len(dati)


def upsert_fng(conn, righe, fonte="alternative.me"):
    """righe: iterabile di (date, valore)."""
    ora = _ora()
    dati = [(g.isoformat(), int(v), fonte, ora) for g, v in righe]
    conn.executemany("INSERT INTO fng(data, valore, fonte, aggiornato_il) VALUES (?,?,?,?) "
                     "ON CONFLICT(data) DO UPDATE SET valore=excluded.valore, "
                     "fonte=excluded.fonte, aggiornato_il=excluded.aggiornato_il", dati)
    conn.commit()
    return len(dati)

# --------------------------------------------------------------- lettura

def conteggi(conn):
    return {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in TABELLE}


def ultima_data(conn, tabella):
    riga = conn.execute(f"SELECT MAX(data) AS d FROM {tabella}").fetchone()
    return datetime.date.fromisoformat(riga["d"]) if riga and riga["d"] else None


def prima_data(conn, tabella):
    riga = conn.execute(f"SELECT MIN(data) AS d FROM {tabella}").fetchone()
    return datetime.date.fromisoformat(riga["d"]) if riga and riga["d"] else None


def serie_prezzi(conn):
    """Ritorna (dates, chiusure, fonti) ordinate per data."""
    righe = conn.execute("SELECT data, chiusura, fonte FROM prezzi ORDER BY data").fetchall()
    return ([datetime.date.fromisoformat(r["data"]) for r in righe],
            [r["chiusura"] for r in righe],
            [r["fonte"] for r in righe])


def serie_mvrv(conn):
    """Ritorna (dates, mvrv, market_cap, price_usd) ordinate per data."""
    righe = conn.execute("SELECT data, mvrv, market_cap, price_usd FROM mvrv ORDER BY data").fetchall()
    return ([datetime.date.fromisoformat(r["data"]) for r in righe],
            [r["mvrv"] for r in righe], [r["market_cap"] for r in righe], [r["price_usd"] for r in righe])


def serie_fng(conn):
    righe = conn.execute("SELECT data, valore FROM fng ORDER BY data").fetchall()
    return ([datetime.date.fromisoformat(r["data"]) for r in righe], [r["valore"] for r in righe])

# ------------------------------------------------------------- impostazioni

def leggi_impostazione(conn, chiave, predefinito=None):
    riga = conn.execute("SELECT valore FROM impostazioni WHERE chiave=?", (chiave,)).fetchone()
    return riga["valore"] if riga else predefinito


def scrivi_impostazione(conn, chiave, valore):
    conn.execute("INSERT INTO impostazioni(chiave, valore, aggiornato_il) VALUES (?,?,?) "
                 "ON CONFLICT(chiave) DO UPDATE SET valore=excluded.valore, "
                 "aggiornato_il=excluded.aggiornato_il", (chiave, str(valore), _ora()))
    conn.commit()
    return valore


# ----------------------------------------------------------------- registro

def scrivi_registro(conn, giorno, stato, punteggi, prezzo, indicatori, messaggio, inviato, esito):
    """Una riga al giorno: cosa ha visto il bot, cosa ha deciso e cosa ha detto (P1 / F6.1).

    Non e' un log tecnico: e' la memoria che fra dodici mesi permettera' di fare l'autopsia
    prevista dal charter (D20). Senza questa riga, quella verifica non e' ricostruibile.
    """
    import json as _json

    conn.execute(
        "INSERT INTO registro(data, stato, punteggio_economico, punteggio_caro, moltiplicatore, "
        "prezzo, indicatori, messaggio, inviato, esito, scritto_il) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(data) DO UPDATE SET "
        "stato=excluded.stato, punteggio_economico=excluded.punteggio_economico, "
        "punteggio_caro=excluded.punteggio_caro, moltiplicatore=excluded.moltiplicatore, "
        "prezzo=excluded.prezzo, indicatori=excluded.indicatori, messaggio=excluded.messaggio, "
        "inviato=excluded.inviato, esito=excluded.esito, scritto_il=excluded.scritto_il",
        (giorno.isoformat(), stato, punteggi.get("economico"), punteggi.get("caro"),
         punteggi.get("moltiplicatore"), prezzo, _json.dumps(indicatori, default=str),
         messaggio, 1 if inviato else 0, esito, _ora()))
    conn.commit()


def ultimo_stato_registrato(conn):
    """Lo stato dell'ultimo giorno registrato: serve a capire se oggi e' cambiato qualcosa."""
    riga = conn.execute("SELECT data, stato FROM registro ORDER BY data DESC LIMIT 1").fetchone()
    if not riga:
        return None, None
    return datetime.date.fromisoformat(riga["data"]), riga["stato"]


def righe_registro(conn, limite=10):
    return conn.execute("SELECT data, stato, punteggio_economico, prezzo, inviato "
                        "FROM registro ORDER BY data DESC LIMIT ?", (limite,)).fetchall()


# ------------------------------------------------------- primo caricamento

def _leggi_csv(percorso, colonne):
    with open(percorso, newline="", encoding="utf-8") as fh:
        for riga in csv.DictReader(fh):
            yield (datetime.date.fromisoformat(riga["date"][:10]),
                   *[riga[c] for c in colonne])


def bootstrap_da_csv(conn, forza=False):
    """Carica nel database i tre CSV gia' validati in `data/` (una volta sola).

    Non riscarica niente dalla rete: e' la regola del progetto (CLAUDE.md §4).
    Ritorna un dizionario {tabella: righe_caricate}; 0 se la tabella era gia' piena.
    """
    caricate = {}
    if forza or conteggi(conn)["prezzi"] == 0:
        righe = [(g, float(c)) for g, c in _leggi_csv(PRICES_COINBASE, ["close"])]
        caricate["prezzi"] = upsert_prezzi(conn, righe, "coinbase (csv storico)")
    else:
        caricate["prezzi"] = 0
    if forza or conteggi(conn)["mvrv"] == 0:
        righe = [(g, float(m), float(mc), float(p))
                 for g, m, mc, p in _leggi_csv(MVRV_COINMETRICS, ["mvrv", "market_cap_usd", "price_usd"])]
        caricate["mvrv"] = upsert_mvrv(conn, righe, "coinmetrics (csv storico)")
    else:
        caricate["mvrv"] = 0
    if forza or conteggi(conn)["fng"] == 0:
        righe = [(g, int(v)) for g, v in _leggi_csv(FNG_ALTERNATIVE_ME, ["fng"])]
        caricate["fng"] = upsert_fng(conn, righe, "alternative.me (csv storico)")
    else:
        caricate["fng"] = 0
    conn.execute("INSERT INTO meta(chiave, valore) VALUES ('bootstrap', ?) "
                 "ON CONFLICT(chiave) DO UPDATE SET valore=excluded.valore", (_ora(),))
    conn.commit()
    return caricate

# ------------------------------------------------------ aggiornamento rete

def aggiorna_da_rete(conn, oggi=None, timeout=20, tentativi=3, fonti=("prezzi", "mvrv", "fng")):
    """Scarica SOLO i giorni mancanti e li scrive. Non solleva eccezioni.

    Ritorna un rapporto:
        {"prezzi": {"nuove": 2, "fonte": "coinbase", "errore": None, "nota": None, "ultima": date}, ...}
    Cosi' il bot puo' decidere cosa dire: una fonte giu' non deve zittire il messaggio (F2.6).

    Nota importante sul "gia' aggiornato": la candela di oggi e' ancora aperta e l'MVRV del
    giorno T arriva il giorno T+1, quindi il dato piu' recente che puo' esistere e' quello di
    IERI. Se l'archivio ha gia' ieri, non si chiama la rete: chiamarla restituirebbe zero righe
    e verrebbe scambiata per un guasto.
    """
    oggi = oggi or datetime.datetime.now(datetime.timezone.utc).date()
    rapporto = {}

    ieri = oggi - datetime.timedelta(days=1)

    if "prezzi" in fonti:
        voce = {"nuove": 0, "fonte": None, "errore": None, "nota": None, "ultima": None}
        ultima = ultima_data(conn, "prezzi")
        da = (ultima + datetime.timedelta(days=1)) if ultima else oggi - datetime.timedelta(days=400)
        if ultima is not None and ultima >= ieri:
            voce["nota"] = f"gia' aggiornato all'ultima candela chiusa ({ultima})"
        elif da <= oggi:
            try:
                righe, fonte, errori = fetchers.prezzo_con_fallback(
                    da, oggi, timeout=timeout, tentativi=tentativi)
                voce["nuove"] = upsert_prezzi(conn, righe, fonte)
                voce["fonte"] = fonte
                if errori:
                    voce["errore"] = "fallback usato: " + " | ".join(str(e) for e in errori)
            except fetchers.FetchError as exc:
                voce["errore"] = str(exc)
        voce["ultima"] = ultima_data(conn, "prezzi")
        rapporto["prezzi"] = voce

    if "mvrv" in fonti:
        voce = {"nuove": 0, "fonte": "coinmetrics", "errore": None, "nota": None, "ultima": None}
        ultima = ultima_data(conn, "mvrv")
        da = (ultima + datetime.timedelta(days=1)) if ultima else oggi - datetime.timedelta(days=400)
        if ultima is not None and ultima >= ieri:
            voce["nota"] = f"gia' aggiornato al dato piu' recente possibile ({ultima}, ritardo T+1)"
        elif da <= oggi:
            try:
                righe = fetchers.mvrv_coinmetrics(da, oggi, timeout=timeout, tentativi=tentativi)
                voce["nuove"] = upsert_mvrv(conn, righe)
            except fetchers.FetchError as exc:
                voce["errore"] = str(exc)
        voce["ultima"] = ultima_data(conn, "mvrv")
        rapporto["mvrv"] = voce

    if "fng" in fonti:
        voce = {"nuove": 0, "fonte": "alternative.me", "errore": None, "nota": None, "ultima": None}
        ultima = ultima_data(conn, "fng")
        if ultima is not None and ultima >= oggi:
            voce["nota"] = f"gia' aggiornato a oggi ({ultima})"
        elif ultima is None or ultima < oggi:
            # l'API non filtra per data: si chiedono gli ultimi giorni e si scrive cio' che manca
            giorni = 0 if ultima is None else min(max((oggi - ultima).days + 2, 2), 400)
            try:
                righe = fetchers.fear_and_greed(limite=giorni, timeout=timeout, tentativi=tentativi)
                nuove = [(g, v) for g, v in righe if ultima is None or g > ultima]
                voce["nuove"] = upsert_fng(conn, nuove) if nuove else 0
            except fetchers.FetchError as exc:
                voce["errore"] = str(exc)
        voce["ultima"] = ultima_data(conn, "fng")
        rapporto["fng"] = voce

    return rapporto
