"""Genera i messaggi del bot su date storiche — verifica F3.1 / F3.3 del piano.

    python3 backtest/messaggi_storici.py            # le dieci date di riferimento
    python3 backtest/messaggi_storici.py 2026-06-29 # una data qualsiasi

Serve a fare la cosa che il piano chiede in chiaro: **stampare i messaggi e rileggerli**.
Si capiscono? Dicono anche i limiti? Non sembrano ordini?

Va messo in `backtest/` perche' e' uno strumento di ricerca: legge i CSV di `data/`, non il
database del bot, e non manda niente a nessuno.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import config
from botbtc import dataset, engine, messaggi

# Parametri della regola, da docs/04 §1 (soglie calibrate sulla quota di giorni, mai sulle date)
PARAMETRI = config.parametri_motore()

# Dieci date scelte per coprire tutti i casi che il bot deve saper raccontare:
# minimi di ciclo, massimi, inizio rialzo, il caso che ha fatto nascere il progetto, e oggi.
DATE_DI_RIFERIMENTO = [
    ("2018-12-15", "minimo di ciclo"),
    ("2019-06-26", "rimbalzo dopo il minimo"),
    ("2020-03-13", "crollo del covid"),
    ("2020-12-30", "inizio del rialzo: il caso difficile per il freno"),
    ("2021-11-08", "massimo di ciclo"),
    ("2022-06-18", "mercato orso profondo"),
    ("2022-11-09", "minimo di ciclo"),
    ("2025-10-06", "massimo di ciclo (presunto)"),
    ("2026-06-29", "il caso che ha fatto nascere il progetto"),
    (None, "oggi (ultimo giorno disponibile)"),
]


def prepara():
    ds = dataset.carica_da_csv(serie="coinmetrics")
    dataset.aggiungi_percentili(ds, 1460)
    percentili = [dataset.percentili_del_giorno(ds, i) for i in range(len(ds))]
    valori = [{k: ds.ind.get(k, [None] * len(ds))[i] for k in engine.PESI} for i in range(len(ds))]
    righe = engine.serie_stati(percentili, PARAMETRI, valori)
    return ds, righe


def stampa_per_data(ds, righe, giorno, etichetta=""):
    indice = ds.indice(giorno)
    foto = dataset.fotografia(ds, ds.dates[indice])
    precedente = engine.NORMALE
    stato_oggi = righe[indice].get("stato_confermato")
    for j in range(indice - 1, max(0, indice - 400), -1):
        passato = righe[j].get("stato_confermato")
        if passato and passato != stato_oggi:
            precedente = passato
            break

    titolo = f" {ds.dates[indice]} — {etichetta} ".center(100, "=")
    print("\n" + titolo)

    print("\n--- POLSO (quotidiano, deve stare in due o tre righe) " + "-" * 45)
    testo = messaggi.polso(ds, righe, indice, foto, PARAMETRI)
    print(testo)
    print(f"[{len(testo.splitlines())} righe, {len(testo)} caratteri]")

    print("\n--- CAMBIO DI STATO (solo quando cambia davvero) " + "-" * 49)
    testo = messaggi.cambio_stato(ds, righe, indice, foto, PARAMETRI, precedente)
    print(testo)
    print(f"[{len(testo)} caratteri]")

    print("\n--- ANALISI COMPLETA (su richiesta, un solo messaggio Telegram) " + "-" * 34)
    testo = messaggi.analisi_completa(ds, righe, indice, foto, PARAMETRI)
    print(testo)
    print(f"[{len(testo)} caratteri, limite Telegram 4096]")


def main(argv):
    ds, righe = prepara()
    if argv:
        for testo in argv:
            stampa_per_data(ds, righe, datetime.date.fromisoformat(testo), "data richiesta")
        return 0
    for giorno, etichetta in DATE_DI_RIFERIMENTO:
        data = ds.dates[-1] if giorno is None else datetime.date.fromisoformat(giorno)
        stampa_per_data(ds, righe, data, etichetta)
    print("\n" + "=" * 100)
    print("Ora la parte che nessun test può fare al posto tuo: rileggerli.")
    print("  1. si capiscono senza conoscere gli indicatori?")
    print("  2. dicono anche i limiti, o promettono?")
    print("  3. sembrano ordini? (non devono: il bot descrive e suggerisce uno sforzo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
