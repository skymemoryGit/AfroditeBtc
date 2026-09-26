"""Prova REALE delle tre fonti (F1.1) — richiede rete.

Non gira nel sandbox di Claude ne' nella shell del ponte: quegli ambienti non raggiungono
gli host (CLAUDE.md §10). Si lancia dal PC dell'utente o dal VPS:

    python3 tests/prova_rete.py            # solo lettura: interroga le fonti e stampa
    python3 tests/prova_rete.py --aggiorna # aggiorna davvero il database del bot

Stampa volutamente in ASCII puro per non litigare con la console di Windows.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from botbtc import dataset, fetchers, sanity, store


def prova_fonti(giorni=6):
    oggi = datetime.datetime.now(datetime.timezone.utc).date()
    da = oggi - datetime.timedelta(days=giorni)
    esiti = []

    print(f"Oggi (UTC): {oggi}\n")

    for nome, funzione in (("coinbase", fetchers.prezzo_coinbase), ("binance", fetchers.prezzo_binance)):
        try:
            righe = funzione(da, oggi)
            esiti.append((nome, True, f"{len(righe)} candele chiuse, ultima {righe[-1][0]} = {righe[-1][1]:,.2f}"))
        except fetchers.FetchError as exc:
            esiti.append((nome, False, str(exc)))

    try:
        righe = fetchers.fear_and_greed(limite=giorni)
        esiti.append(("alternative.me", True, f"{len(righe)} valori, ultimo {righe[-1][0]} = {righe[-1][1]}"))
    except fetchers.FetchError as exc:
        esiti.append(("alternative.me", False, str(exc)))

    try:
        righe = fetchers.mvrv_coinmetrics(da, oggi)
        ultima = righe[-1]
        esiti.append(("coinmetrics", True,
                      f"{len(righe)} giorni, ultimo {ultima[0]} = MVRV {ultima[1]:.4f} "
                      f"(ritardo {(oggi - ultima[0]).days} giorni)"))
    except fetchers.FetchError as exc:
        esiti.append(("coinmetrics", False, str(exc)))

    for nome, ok, dettaglio in esiti:
        print(f"  [{'OK ' if ok else 'KO '}] {nome:16} {dettaglio}")
    return all(ok for _, ok, _ in esiti)


def aggiorna(percorso_db=None):
    conn = store.apri(percorso_db)
    if store.conteggi(conn)["prezzi"] == 0:
        print("\nArchivio vuoto: carico prima i CSV storici.")
        print("  caricate:", store.bootstrap_da_csv(conn))
    print("\nPrima:", {t: str(store.ultima_data(conn, t)) for t in store.TABELLE})
    rapporto = store.aggiorna_da_rete(conn)
    for fonte, voce in rapporto.items():
        print(f"  {fonte:8} nuove={voce['nuove']:3}  ultima={voce['ultima']}  "
              f"fonte={voce['fonte']}  errore={voce['errore']}")
    print("\nControlli di sanita':")
    print(sanity.stampa(sanity.rapporto(conn)))
    ds = dataset.carica(conn)
    print("\nFotografia:", dataset.riga_di_stato(dataset.fotografia(ds)))
    conn.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aggiorna", action="store_true", help="scrive davvero nel database del bot")
    p.add_argument("--db", default=None)
    args = p.parse_args()
    tutto_ok = prova_fonti()
    if args.aggiorna:
        aggiorna(args.db)
    raise SystemExit(0 if tutto_ok else 1)
