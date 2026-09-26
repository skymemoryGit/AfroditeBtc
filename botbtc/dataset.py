"""Dal database agli indicatori (F1.4 del piano).

Questo modulo e' il ponte: legge le serie dalla cache SQLite, le allinea e chiama
`botbtc/indicators.py`. Nessun calcolo nuovo vive qui — gli indicatori restano uno solo,
condiviso fra backtest e bot, come deciso in D11/D14.

Tre punti delicati, risolti qui una volta per tutte:

1. **Due assi temporali diversi.** Il prezzo (Coinbase) parte dal 2017 ed e' aggiornato a
   ieri; l'MVRV (CoinMetrics) parte dal 2010 ma arriva a T-1 per costruzione. Gli indicatori
   dell'MVRV si calcolano quindi **sul loro asse**, dove la serie e' continua, e solo dopo
   vengono riportati sull'asse dei prezzi. Cosi' il percentile a 4 anni usa tutta la storia
   disponibile e non si rompe quando l'ultimo giorno di MVRV manca.

2. **Nucleo di solo prezzo** (F2.6): Mayer, 200-WMA, drawdown 365, RSI giornaliero e
   settimanale, Pi Cycle si calcolano dal solo prezzo, che c'e' sempre. MVRV e Fear & Greed
   sono "arricchimento": se mancano, `fotografia()` lo dichiara e il bot parla lo stesso.

3. **Niente mescolanze di serie di prezzo** (D12): si sceglie `serie="coinbase"` (default,
   quella del bot live) oppure `serie="coinmetrics"` (PriceUSD, storia dal 2010, usata per
   riprodurre i numeri di `docs/02`). Mai le due insieme dentro lo stesso calcolo.
"""

import datetime
import os

from . import indicators as ind
from . import store

FINESTRE_PERCENTILE = (730, 1095, 1460, 1825)   # 2, 3, 4, 5 anni — criterio (g) di F2.3


class Dataset:
    """Serie allineate + indicatori gia' calcolati, tutti sull'asse delle date del prezzo."""

    def __init__(self, dates, prezzi, fonte_prezzo, indicatori, meta):
        self.dates = dates
        self.prezzi = prezzi
        self.fonte_prezzo = fonte_prezzo
        self.ind = indicatori
        self.meta = meta
        self._pos = {d: i for i, d in enumerate(dates)}

    def __len__(self):
        return len(self.dates)

    def indice(self, giorno=None):
        """Indice del giorno richiesto, o dell'ultimo disponibile."""
        if giorno is None:
            return len(self.dates) - 1
        if giorno in self._pos:
            return self._pos[giorno]
        raise KeyError(f"{giorno} non e' nella serie ({self.dates[0]} -> {self.dates[-1]})")

    def valore(self, chiave, giorno=None):
        return self.ind[chiave][self.indice(giorno)]


def _nome_fonte(fonti):
    """Etichetta leggibile della serie di prezzo: l'utente non deve leggere 'coinbase (csv storico)'."""
    insieme = set(fonti)
    nomi = []
    if any("coinbase" in f for f in insieme):
        nomi.append("Coinbase")
    if any("binance" in f for f in insieme):
        nomi.append("Binance (fallback)")
    for altra in sorted(f for f in insieme if "coinbase" not in f and "binance" not in f):
        nomi.append(altra)
    return " + ".join(nomi) or "sconosciuta"


def _carica_trends():
    """Legge data/google_trends_bitcoin.csv se c'e'. Non e' un errore se manca: e' contesto."""
    from .paths import DATA_DIR

    percorso = os.path.join(DATA_DIR, "google_trends_bitcoin.csv")
    if not os.path.exists(percorso):
        return [], []
    dates, valori = ind.load_csv(percorso, cols=("interesse",))
    return dates, valori["interesse"]


def _allinea_a_gradini(dates_obiettivo, dates_sorgente, valori, ritardo_giorni=0):
    """Serie a bassa frequenza (mensile) riportata sui giorni, tenendo l'ultimo valore NOTO.

    `ritardo_giorni` e' quanto tempo passa prima che quel punto sia definitivo: per Google Trends
    il valore del mese M si considera disponibile dal mese successivo.
    """
    coppie = sorted(zip(dates_sorgente, valori))
    fuori, j, corrente = [], 0, None
    for giorno in dates_obiettivo:
        limite = giorno - datetime.timedelta(days=ritardo_giorni)
        while j < len(coppie) and coppie[j][0] <= limite:
            corrente = coppie[j][1]
            j += 1
        fuori.append(corrente)
    return fuori


def _allinea(dates_obiettivo, dates_sorgente, valori):
    """Riporta una serie sul calendario di un'altra. Nessun riempimento in avanti:
    se un giorno non c'e', resta None e chi legge lo deve dichiarare."""
    mappa = dict(zip(dates_sorgente, valori))
    return [mappa.get(g) for g in dates_obiettivo]


def _costruisci(dates, prezzi, fonte_prezzo, d_m, mvrv, mcap, d_f, fng, finestre_percentile):
    """Parte comune fra `carica` (database) e `carica_da_csv` (file): allinea e calcola."""
    if not dates:
        raise ValueError("nessun prezzo disponibile: serve un bootstrap dai CSV (store.bootstrap_da_csv)")

    # --- nucleo: tutto cio' che si calcola dal solo prezzo
    indicatori = ind.compute_all(dates, prezzi)

    meta = {"serie_prezzo": fonte_prezzo,
            "prezzo_da": dates[0], "prezzo_a": dates[-1],
            "mvrv_da": d_m[0] if d_m else None, "mvrv_a": d_m[-1] if d_m else None}

    # --- arricchimento MVRV: calcolato sul suo asse continuo, poi riportato qui
    if d_m:
        meta["mvrv_buchi"] = len(ind.check_daily_continuity(d_m))
        z = ind.mvrv_zscore_expanding(mcap, mvrv)
        indicatori["mvrv"] = _allinea(dates, d_m, mvrv)
        indicatori["mvrv_z"] = _allinea(dates, d_m, z)
        indicatori["realized_cap"] = _allinea(dates, d_m, ind.realized_cap(mcap, mvrv))
        for w in finestre_percentile:
            indicatori[f"mvrv_pct{w}"] = _allinea(dates, d_m, ind.percentile_rank(mvrv, w))
        indicatori["mvrv_pct"] = indicatori.get("mvrv_pct1460")   # finestra predefinita: 4 anni
    else:
        meta["mvrv_buchi"] = None

    # --- contesto Google Trends (mensile, riscalato: vedi backtest/aggiorna_google_trends.py)
    d_g, gt = _carica_trends()
    if d_g:
        # il punto del mese M e' definitivo solo a mese concluso: lo si usa dal mese SUCCESSIVO,
        # altrimenti il bot userebbe un dato che quel giorno non poteva avere (lookahead)
        indicatori["trends"] = _allinea_a_gradini(dates, d_g, gt, ritardo_giorni=31)
        meta["trends_da"], meta["trends_a"] = d_g[0], d_g[-1]
    else:
        indicatori["trends"] = [None] * len(dates)
        meta["trends_da"] = meta["trends_a"] = None

    # --- arricchimento Fear & Greed
    indicatori["fng"] = _allinea(dates, d_f, fng)
    meta["fng_da"] = d_f[0] if d_f else None
    meta["fng_a"] = d_f[-1] if d_f else None

    return Dataset(dates, prezzi, fonte_prezzo, indicatori, meta)


def _taglia(dates, prezzi, da, a):
    if not (da or a):
        return dates, prezzi
    tenuti = [i for i, g in enumerate(dates) if (da is None or g >= da) and (a is None or g <= a)]
    return [dates[i] for i in tenuti], [prezzi[i] for i in tenuti]


def carica(conn, serie="coinbase", finestre_percentile=FINESTRE_PERCENTILE, da=None, a=None):
    """Costruisce il Dataset dal database (bot live).

    serie: "coinbase" (bot live) oppure "coinmetrics" (PriceUSD, per riprodurre docs/02).
    da/a: taglio opzionale dell'asse temporale.
    """
    d_m, mvrv, mcap, price_usd = store.serie_mvrv(conn)
    if serie == "coinbase":
        dates, prezzi, fonti = store.serie_prezzi(conn)
        fonte_prezzo = _nome_fonte(fonti)
    elif serie == "coinmetrics":
        dates, prezzi, fonte_prezzo = list(d_m), list(price_usd), "coinmetrics (PriceUSD)"
    else:
        raise ValueError(f"serie sconosciuta: {serie!r} (attese 'coinbase' o 'coinmetrics')")
    dates, prezzi = _taglia(dates, prezzi, da, a)
    d_f, fng = store.serie_fng(conn)
    return _costruisci(dates, prezzi, fonte_prezzo, d_m, mvrv, mcap, d_f, fng, finestre_percentile)


def carica_da_csv(serie="coinmetrics", finestre_percentile=FINESTRE_PERCENTILE, da=None, a=None):
    """Come `carica`, ma leggendo direttamente i CSV di `data/`: nessun database.

    Serve agli script di ricerca in `backtest/` (che devono girare ovunque, anche dove SQLite
    non e' utilizzabile) e garantisce che il test storico usi esattamente gli stessi dati
    validati dei documenti.
    """
    from .paths import FNG_ALTERNATIVE_ME, MVRV_COINMETRICS, PRICES_COINBASE

    d_m, colonne = ind.load_csv(MVRV_COINMETRICS, cols=("mvrv", "market_cap_usd", "price_usd"))
    mvrv, mcap, price_usd = colonne["mvrv"], colonne["market_cap_usd"], colonne["price_usd"]
    if serie == "coinmetrics":
        dates, prezzi, fonte_prezzo = list(d_m), list(price_usd), "coinmetrics (PriceUSD, csv)"
    elif serie == "coinbase":
        dates, colonne_p = ind.load_csv(PRICES_COINBASE, cols=("close",))
        prezzi, fonte_prezzo = colonne_p["close"], "coinbase (csv)"
    else:
        raise ValueError(f"serie sconosciuta: {serie!r} (attese 'coinbase' o 'coinmetrics')")
    dates, prezzi = _taglia(dates, prezzi, da, a)
    d_f, colonne_f = ind.load_csv(FNG_ALTERNATIVE_ME, cols=("fng",))
    return _costruisci(dates, prezzi, fonte_prezzo, d_m, mvrv, mcap, d_f, colonne_f["fng"],
                       finestre_percentile)


def aggiungi_percentili(ds, finestra=1460, minimo=365, ingredienti=None):
    """Calcola il percentile sulla finestra mobile di ogni ingrediente del motore (F2.2).

    Scrive in `ds.ind` le chiavi `pct_<ingrediente>` e le restituisce. Orientamento: tutti gli
    ingredienti sono gia' in forma "alto = caro" (il drawdown vale 0 al massimo e -60 in fondo
    al mercato orso, quindi alto = caro senza ribaltarlo).
    Tollera i buchi: Fear & Greed prima del 2018 e MVRV dell'ultimo giorno possono mancare,
    e in quel caso il percentile e' None e il motore degrada con grazia (F2.6).
    """
    from . import engine

    chiavi = ingredienti or tuple(engine.PESI)
    prodotte = {}
    for chiave in chiavi:
        serie = ds.ind.get(chiave)
        if serie is None:
            continue
        prodotte[chiave] = ind.percentile_rank_con_buchi(serie, finestra, minimo)
        ds.ind[f"pct_{chiave}"] = prodotte[chiave]
    ds.meta["finestra_percentile"] = finestra
    return prodotte


def percentili_del_giorno(ds, indice):
    """Dizionario {ingrediente: percentile} pronto per `engine.valuta` (None se manca)."""
    from . import engine

    return {chiave: (ds.ind.get(f"pct_{chiave}") or [None] * len(ds))[indice]
            for chiave in engine.PESI}


# ------------------------------------------------------------- fotografia

NUCLEO = ("mayer", "dd365", "rsi14_d", "rsi14_w", "price_vs_wma200", "pi_ratio")
ARRICCHIMENTO = ("mvrv", "mvrv_pct", "mvrv_z", "fng")


def fotografia(ds, giorno=None):
    """Stato del giorno: valori, ingredienti disponibili e data effettiva di ogni fonte.

    `ingredienti_mancanti` non e' un dettaglio tecnico: e' la riga che il messaggio deve
    contenere quando una fonte non c'e' (F2.6 + F4.3). Il bot parla comunque, ma dice con
    cosa ha deciso.
    """
    i = ds.indice(giorno)
    valori = {"data": ds.dates[i], "prezzo": ds.prezzi[i], "fonte_prezzo": ds.fonte_prezzo}
    presenti, mancanti = [], []
    for chiave in NUCLEO + ARRICCHIMENTO:
        v = ds.ind.get(chiave, [None] * len(ds))[i]
        valori[chiave] = v
        (presenti if v is not None else mancanti).append(chiave)
    valori["ingredienti_presenti"] = presenti
    valori["ingredienti_mancanti"] = mancanti
    valori["nucleo_completo"] = all(valori[c] is not None for c in NUCLEO)

    # data reale dell'ultimo MVRV disponibile (di norma il giorno prima: ritardo strutturale)
    ultima_mvrv = None
    for j in range(i, -1, -1):
        if ds.ind.get("mvrv") and ds.ind["mvrv"][j] is not None:
            ultima_mvrv = ds.dates[j]
            break
    valori["mvrv_data"] = ultima_mvrv
    valori["mvrv_ritardo_giorni"] = (ds.dates[i] - ultima_mvrv).days if ultima_mvrv else None
    return valori


def riga_di_stato(foto):
    """Una riga leggibile per i log e per il --dry-run (il testo vero del bot e' la F3)."""
    def f(chiave, nd=2, suffisso=""):
        v = foto.get(chiave)
        return "n/d" if v is None else f"{v:.{nd}f}{suffisso}"
    pezzi = [f"{foto['data']}", f"prezzo {foto['prezzo']:,.0f}",
             f"Mayer {f('mayer')}", f"dd365 {f('dd365', 1, '%')}",
             f"RSI d/s {f('rsi14_d', 1)}/{f('rsi14_w', 1)}",
             f"P/200WMA {f('price_vs_wma200')}",
             f"MVRV {f('mvrv', 3)} (pct4a {f('mvrv_pct', 1)})",
             f"F&G {f('fng', 0)}"]
    if foto["ingredienti_mancanti"]:
        pezzi.append("MANCANO: " + ", ".join(foto["ingredienti_mancanti"]))
    if foto.get("mvrv_ritardo_giorni"):
        pezzi.append(f"MVRV del {foto['mvrv_data']}")
    return " | ".join(pezzi)
