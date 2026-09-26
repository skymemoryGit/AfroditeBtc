"""Controlli di sanita' sui dati (F1.3 del piano).

A cosa servono: il bot deve accorgersi da solo quando i dati sono rotti o vecchi, e
**dirlo**, invece di calcolare indicatori su una serie sbagliata e mandare un messaggio
che sembra normale. Regola del progetto: mai mostrare un dato vecchio come se fosse di
oggi, mai inventare (CLAUDE.md §4).

Due livelli di gravita':
- `grave`  -> quella fonte non e' utilizzabile per decidere: il bot lo dichiara e, se puo',
              lavora col nucleo di soli prezzi (F2.6);
- `avviso` -> si puo' procedere, ma il messaggio deve dirlo.

Nessun controllo qui dentro tocca la rete o il database: prende liste e restituisce problemi.
"""

import datetime
from collections import namedtuple

Problema = namedtuple("Problema", "gravita fonte tipo messaggio data")


def _d(x):
    return x.isoformat() if isinstance(x, datetime.date) else str(x)

# ------------------------------------------------------- serie giornaliera

def controlla_serie(dates, valori, fonte, salto_max=0.30, oggi=None, max_esempi=3,
                    consenti_buchi=False, salto_assoluto_max=None, minimo_ammesso=0):
    """Ordine, duplicati, buchi, valori impossibili, salti sospetti, date nel futuro.

    `salto_max` e' una variazione RELATIVA e ha senso per un prezzo. Per un indice limitato
    come il Fear & Greed (0-100) il salto va misurato in PUNTI: si passa `salto_assoluto_max`
    e la variazione relativa viene ignorata (da 3 a 8 e' +167 % ma sono 5 punti su 100).
    `minimo_ammesso` e' il valore piu' basso accettabile: 0 per un indice, escluso per un prezzo.
    """
    problemi = []
    oggi = oggi or datetime.datetime.now(datetime.timezone.utc).date()
    if not dates:
        return [Problema("grave", fonte, "serie_vuota", "la serie non contiene nessuna riga", None)]

    fuori_ordine = [dates[i] for i in range(1, len(dates)) if dates[i] <= dates[i - 1]]
    if fuori_ordine:
        problemi.append(Problema("grave", fonte, "ordine",
                                 f"{len(fuori_ordine)} date fuori ordine o duplicate "
                                 f"(prima: {_d(fuori_ordine[0])})", fuori_ordine[0]))

    buchi = [(dates[i - 1], dates[i]) for i in range(1, len(dates))
             if (dates[i] - dates[i - 1]).days > 1]
    if buchi:
        esempi = ", ".join(f"{_d(a)} -> {_d(b)}" for a, b in buchi[:max_esempi])
        mancanti = sum((b - a).days - 1 for a, b in buchi)
        problemi.append(Problema("avviso" if consenti_buchi else "grave", fonte, "buchi",
                                 f"{len(buchi)} interruzioni ({mancanti} giorni mancanti): {esempi}",
                                 buchi[0][1]))

    futuro = [g for g in dates if g > oggi]
    if futuro:
        problemi.append(Problema("grave", fonte, "futuro",
                                 f"{len(futuro)} date nel futuro (prima: {_d(futuro[0])}, oggi {_d(oggi)})",
                                 futuro[0]))

    non_validi = [(g, v) for g, v in zip(dates, valori) if v is None or v < minimo_ammesso]
    if non_validi:
        problemi.append(Problema("grave", fonte, "valore_non_valido",
                                 f"{len(non_validi)} valori nulli o non positivi "
                                 f"(primo: {_d(non_validi[0][0])} = {non_validi[0][1]})",
                                 non_validi[0][0]))

    salti = []
    for i in range(1, len(valori)):
        a, b = valori[i - 1], valori[i]
        if a is None or b is None:
            continue
        if salto_assoluto_max is not None:
            if abs(b - a) > salto_assoluto_max:
                salti.append((dates[i], b - a))
        elif a > 0 and abs(b / a - 1) > salto_max:
            salti.append((dates[i], (b / a - 1) * 100))
    if salti:
        unita = " punti" if salto_assoluto_max is not None else "%"
        limite = (f"{salto_assoluto_max:g} punti" if salto_assoluto_max is not None
                  else f"il {salto_max*100:.0f}%")
        esempi = ", ".join(f"{_d(g)} {v:+.0f}{unita}" for g, v in salti[:max_esempi])
        problemi.append(Problema("avviso", fonte, "salto",
                                 f"{len(salti)} variazioni oltre {limite} in un giorno: {esempi}",
                                 salti[0][0]))
    return problemi

# -------------------------------------------------------------- freschezza

def controlla_freschezza(fonte, ultima, oggi=None, eta_massima_giorni=2, ritardo_atteso=0):
    """La fonte ha un dato abbastanza recente?

    `ritardo_atteso` = giorni di ritardo strutturale della fonte (MVRV: 1, docs/02 §1).
    Il dato piu' recente possibile e' quindi `oggi - ritardo_atteso`.
    """
    oggi = oggi or datetime.datetime.now(datetime.timezone.utc).date()
    if ultima is None:
        return [Problema("grave", fonte, "assente", "nessun dato in archivio", None)]
    eta = (oggi - ultima).days
    if eta > eta_massima_giorni:
        return [Problema("grave", fonte, "vecchio",
                         f"ultimo dato {_d(ultima)}, cioe' {eta} giorni fa "
                         f"(tollerati {eta_massima_giorni}; ritardo strutturale della fonte: {ritardo_atteso})",
                         ultima)]
    if eta > ritardo_atteso:
        return [Problema("avviso", fonte, "in_ritardo",
                         f"ultimo dato {_d(ultima)} ({eta} giorni fa, atteso {ritardo_atteso})", ultima)]
    return []

# -------------------------------------------------------------- confronto

def confronta_serie_prezzi(dates_a, valori_a, dates_b, valori_b, nome_a, nome_b, scarto_max=0.05):
    """Due fonti di prezzo devono raccontare la stessa storia.

    Serve quando si mescolano righe Coinbase e righe Binance (fallback) o si confronta con
    `PriceUSD` di CoinMetrics: se lo scarto medio esplode, una delle due e' sbagliata.
    """
    mappa_b = dict(zip(dates_b, valori_b))
    comuni = [(a, mappa_b[g]) for g, a in zip(dates_a, valori_a) if g in mappa_b and mappa_b[g]]
    if not comuni:
        return [Problema("avviso", f"{nome_a}/{nome_b}", "nessuna_sovrapposizione",
                         "le due serie non hanno giorni in comune", None)]
    scarti = [abs(a / b - 1) for a, b in comuni]
    medio = sum(scarti) / len(scarti)
    if medio > scarto_max:
        return [Problema("grave", f"{nome_a}/{nome_b}", "divergenza",
                         f"scarto medio {medio*100:.1f}% su {len(comuni)} giorni in comune "
                         f"(soglia {scarto_max*100:.0f}%)", None)]
    return []

# ----------------------------------------------------------- rapporto unico

def rapporto(conn, oggi=None, salto_max=0.30, eta_prezzo=2, eta_mvrv=3, eta_fng=3):
    """Esegue tutti i controlli sul database e ritorna la lista dei problemi.

    Importato qui e non in cima per tenere questo modulo utilizzabile anche senza database.
    """
    from . import store

    oggi = oggi or datetime.datetime.now(datetime.timezone.utc).date()
    problemi = []

    d_p, prezzi, fonti = store.serie_prezzi(conn)
    problemi += controlla_serie(d_p, prezzi, "prezzi", salto_max, oggi, minimo_ammesso=1e-9)
    problemi += controlla_freschezza("prezzi", store.ultima_data(conn, "prezzi"), oggi, eta_prezzo, 1)
    miste = sorted(set(fonti))
    if len([f for f in miste if "binance" in f]) and len([f for f in miste if "coinbase" in f]):
        problemi.append(Problema("avviso", "prezzi", "fonti_miste",
                                 "la serie contiene giorni Coinbase e giorni Binance: "
                                 "sono due mercati diversi (BTC-USD contro BTCUSDT)", None))

    d_m, mvrv, mcap, price_usd = store.serie_mvrv(conn)
    problemi += controlla_serie(d_m, mvrv, "mvrv", 0.60, oggi, minimo_ammesso=1e-9)
    problemi += controlla_freschezza("mvrv", store.ultima_data(conn, "mvrv"), oggi, eta_mvrv, 1)
    problemi += confronta_serie_prezzi(d_p, prezzi, d_m, price_usd, "coinbase", "coinmetrics")

    d_f, fng = store.serie_fng(conn)
    # la storia F&G ha buchi noti alla fonte (2018-04-14/15/16, 2024-10-26): sono avvisi, non errori
    # il Fear & Greed e' un indice 0-100: il salto si misura in punti, non in percentuale
    problemi += controlla_serie(d_f, fng, "fng", oggi=oggi, consenti_buchi=True,
                                salto_assoluto_max=40, minimo_ammesso=0)
    problemi += controlla_freschezza("fng", store.ultima_data(conn, "fng"), oggi, eta_fng, 0)
    fuori_scala = [(g, v) for g, v in zip(d_f, fng) if not 0 <= v <= 100]
    if fuori_scala:
        problemi.append(Problema("grave", "fng", "fuori_scala",
                                 f"{len(fuori_scala)} valori fuori dall'intervallo 0-100", fuori_scala[0][0]))
    return problemi


def gravi(problemi):
    return [p for p in problemi if p.gravita == "grave"]


def fonti_compromesse(problemi):
    """Insieme delle fonti che non si possono usare per decidere."""
    return {p.fonte for p in gravi(problemi)}


def stampa(problemi):
    if not problemi:
        return "nessun problema rilevato"
    righe = []
    for p in problemi:
        righe.append(f"[{p.gravita.upper():6}] {p.fonte:10} {p.tipo:20} {p.messaggio}")
    return "\n".join(righe)
