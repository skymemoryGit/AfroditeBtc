"""Scarica l'interesse di ricerca per "bitcoin" da Google Trends (data/google_trends_bitcoin.csv).

    python3 backtest/aggiorna_google_trends.py

Perche' sta in `backtest/` e non dentro `botbtc/`:
- usa `pytrends`, che e' una **dipendenza esterna** e per giunta un endpoint interno di Google
  ricostruito, non un'API documentata (la regola del progetto e' D2: niente scraping, solo API
  pubbliche). Tenendolo qui, il bot in esercizio **legge solo il CSV** e non dipende da pytrends:
  se Google cambia qualcosa, il report continua ad arrivare col dato dell'ultimo aggiornamento,
  dichiarato come tale;
- Google restituisce dati **mensili** per finestre lunghe e settimanali per finestre corte, e
  l'indice e' **riscalato 0-100 sulla finestra richiesta**: due tirate diverse non sono
  confrontabili. Per questo il file si ricuce su una sovrapposizione, una volta sola, qui.

Aggiornamento consigliato: una volta al mese. Il dato del mese in corso e' parziale e va ignorato.
"""

import csv
import datetime
import os
import sys
import time

DESTINAZIONE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                            "data", "google_trends_bitcoin.csv")
FINESTRE = ("2015-01-01 2021-12-31", "2021-01-01 {oggi}")


def scarica(tentativi=3, pausa=20):
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("pytrends non installato: pip install pytrends")
        return None
    import pandas as pd

    oggi = datetime.date.today().isoformat()
    richiesta = TrendReq(hl="en-US", tz=0)
    pezzi = []
    for finestra in FINESTRE:
        finestra = finestra.format(oggi=oggi)
        for tentativo in range(1, tentativi + 1):
            try:
                richiesta.build_payload(kw_list=["bitcoin"], timeframe=finestra)
                serie = richiesta.interest_over_time()["bitcoin"]
                print(f"  {finestra}: {len(serie)} punti, {serie.index.min().date()} -> {serie.index.max().date()}")
                pezzi.append(serie)
                break
            except Exception as exc:                      # pytrends alza di tutto, anche 429
                print(f"  {finestra}: tentativo {tentativo} fallito ({type(exc).__name__})")
                if tentativo == tentativi:
                    return None
                time.sleep(pausa * tentativo)
        time.sleep(10)

    vecchio, nuovo = pezzi
    comune = vecchio.index.intersection(nuovo.index)
    if len(comune) < 6:
        print(f"  sovrapposizione troppo corta ({len(comune)} punti): non ricucio")
        return None
    fattore = vecchio.loc[comune].sum() / nuovo.loc[comune].sum()
    unito = pd.concat([vecchio[vecchio.index < nuovo.index.min()], nuovo * fattore])
    unito = unito / unito.max() * 100
    print(f"  ricucito con fattore {fattore:.4f}; massimo (100) il {unito.idxmax().date()}")
    return unito


def salva(serie):
    percorso = os.path.abspath(DESTINAZIONE)
    with open(percorso, "w", newline="", encoding="utf-8") as fh:
        scrittore = csv.writer(fh)
        scrittore.writerow(["date", "interesse"])
        for giorno, valore in serie.items():
            scrittore.writerow([giorno.date().isoformat(), f"{valore:.1f}"])
    print(f"  salvato {percorso}: {len(serie)} punti")


if __name__ == "__main__":
    print("Google Trends — interesse di ricerca per 'bitcoin'")
    serie = scarica()
    if serie is None:
        print("  aggiornamento non riuscito: il file precedente resta valido, col suo ritardo.")
        raise SystemExit(1)
    salva(serie)
