"""Backup giornaliero del database del bot (F5.2 del piano).

Il database e' la memoria del progetto: il registro giornaliero (cosa ha detto il bot e quando) non
si puo' ricostruire dopo. Questo script ne fa una copia al giorno e tiene le ultime 30.

Usa l'API di backup di SQLite, che e' sicura anche se il bot sta scrivendo in quel momento (una
copia del file fatta a meta' di una scrittura potrebbe essere rovinata). Dopo la copia controlla
che il file sia integro. Solo libreria standard.

    python3 deploy/backup_db.py                         # in ~/backup-aphroditebtc, ultime 30 copie
    python3 deploy/backup_db.py --dest /altra/cartella --tieni 60
"""

import argparse
import datetime
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
from botbtc.paths import DB_DEFAULT  # noqa: E402

PREFISSO = "botbtc-"


def main(argv=None):
    p = argparse.ArgumentParser(description="Backup del database di AphroditeBTC")
    p.add_argument("--db", default=DB_DEFAULT, help="database da copiare")
    p.add_argument("--dest", default=os.path.expanduser("~/backup-aphroditebtc"))
    p.add_argument("--tieni", type=int, default=30, help="quante copie tenere (default 30)")
    a = p.parse_args(argv)

    if not os.path.exists(a.db):
        print(f"ERRORE: database non trovato: {a.db}")
        return 1
    os.makedirs(a.dest, exist_ok=True)
    destinazione = os.path.join(a.dest, f"{PREFISSO}{datetime.date.today().isoformat()}.sqlite3")

    sorgente = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    copia = sqlite3.connect(destinazione)
    try:
        with copia:
            sorgente.backup(copia)
    finally:
        copia.close()
        sorgente.close()

    controllo = sqlite3.connect(f"file:{destinazione}?mode=ro", uri=True)
    try:
        esito = controllo.execute("PRAGMA integrity_check").fetchone()[0]
        try:
            righe = controllo.execute("SELECT count(*) FROM registro").fetchone()[0]
        except sqlite3.OperationalError:
            righe = "n/d"
    finally:
        controllo.close()
    if esito != "ok":
        print(f"ERRORE: la copia {destinazione} non e' integra: {esito}")
        return 1

    copie = sorted(f for f in os.listdir(a.dest) if f.startswith(PREFISSO) and f.endswith(".sqlite3"))
    for vecchia in copie[:-a.tieni] if a.tieni > 0 else []:
        os.remove(os.path.join(a.dest, vecchia))
    print(f"backup ok: {destinazione} · integrita' ok · righe di registro: {righe} · "
          f"copie tenute: {min(len(copie), a.tieni)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
