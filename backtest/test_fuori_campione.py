"""Test fuori campione (walk-forward): la regola funziona su anni che non aveva visto? (D41)

    python3 backtest/test_fuori_campione.py

Il problema che risolve: le soglie del motore sono state calibrate su TUTTA la storia, giugno 2026
compreso. Anche se nessun calcolo usa il futuro (lo dimostra tests/test_lookahead.py), noi il futuro
di quegli anni lo conoscevamo quando abbiamo scritto la regola. Quindi "giugno 2026 si accende" e'
una verifica meno forte di quanto sembri: era dentro i dati di calibrazione.

La prova onesta: si calibrano le soglie usando SOLO i giorni fino a una certa data, si congelano, e
si guarda cosa sarebbe successo DOPO — su anni che la calibrazione non ha mai visto. E' la cosa piu'
vicina a "mettere il bot in esercizio nel 2020 e aspettare", che si possa fare oggi.

E' legittimo calibrare su un sottoinsieme di giorni solo perche' il calcolo del punteggio di un
giorno non dipende dai giorni successivi: lo prova tests/test_lookahead.py.
"""

import datetime
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from botbtc import dataset, engine

MASSIMI = [datetime.date(2017, 12, 16), datetime.date(2021, 4, 13),
           datetime.date(2021, 11, 8), datetime.date(2025, 10, 6)]
CASI = {"dicembre 2018": (datetime.date(2018, 12, 1), datetime.date(2018, 12, 31)),
        "marzo 2020": (datetime.date(2020, 3, 1), datetime.date(2020, 3, 31)),
        "novembre 2022": (datetime.date(2022, 11, 1), datetime.date(2022, 11, 30)),
        "giugno 2026": (datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))}


def quantile(valori, q):
    valori = sorted(valori)
    pos = q * (len(valori) - 1)
    b, a = int(pos), min(int(pos) + 1, len(valori) - 1)
    return valori[b] + (valori[a] - valori[b]) * (pos - b)


def main():
    ds = dataset.carica_da_csv(serie="coinmetrics")
    dataset.aggiungi_percentili(ds, 1460)
    percentili = [dataset.percentili_del_giorno(ds, i) for i in range(len(ds))]
    base = engine.Parametri(durata_minima_caro=60)
    grezzi = [engine.valuta(p, base) for p in percentili]

    print("=" * 100)
    print("TEST FUORI CAMPIONE — soglie calibrate solo sul passato, poi congelate")
    print("=" * 100)

    for fine_calibrazione in (datetime.date(2018, 12, 31), datetime.date(2020, 12, 31),
                              datetime.date(2022, 12, 31)):
        # 1) calibrazione: SOLO giorni fino a fine_calibrazione, stesso metodo di sempre (quota)
        eco = [g["punteggio_economico"] for d, g in zip(ds.dates, grezzi)
               if d <= fine_calibrazione and g["punteggio_economico"] is not None]
        caro = [g["punteggio_caro"] for d, g in zip(ds.dates, grezzi)
                if d <= fine_calibrazione and g["punteggio_caro"] is not None]
        par = base.copia(soglia_straordinario=round(quantile(eco, 0.88), 4),
                         soglia_freno=round(quantile(caro, 0.80), 4))
        righe = engine.serie_stati(percentili, par)
        stati = {ds.dates[i]: righe[i].get("stato_confermato") for i in range(len(ds))}

        # 2) valutazione: SOLO sui giorni dopo
        dopo = {d: s for d, s in stati.items() if d > fine_calibrazione and s != engine.SCONOSCIUTO}
        quota = 100 * sum(1 for s in dopo.values() if s == engine.STRAORDINARIO) / len(dopo)
        print(f"\nCalibrato fino al {fine_calibrazione} ({len(eco)} giorni) → soglie "
              f"{par.soglia_straordinario:.4f} / {par.soglia_freno:.4f}")
        print(f"  giorni mai visti dalla calibrazione: {len(dopo)} "
              f"({min(dopo)} → {max(dopo)})")
        print(f"  quota straordinario sui giorni nuovi: {quota:.1f}% (atteso 10-15%)")

        for nome, (a, b) in CASI.items():
            if a <= fine_calibrazione:
                continue
            accesi = [d for d, s in dopo.items() if a <= d <= b and s == engine.STRAORDINARIO]
            print(f"  {'OK ' if accesi else 'NO '} {nome}: "
                  + (f"{len(accesi)} giorni accesi, dal {min(accesi)}" if accesi else "MAI acceso"))
        for m in MASSIMI:
            if m <= fine_calibrazione:
                continue
            accesi = [d for d, s in dopo.items()
                      if m - datetime.timedelta(days=90) <= d <= m and s == engine.STRAORDINARIO]
            print(f"  {'OK ' if not accesi else 'NO '} nessuno straordinario nei 90 giorni prima del "
                  f"massimo {m}" + ("" if not accesi else f" — {len(accesi)} giorni"))
        fwd = [(ds.prezzi[i + 365] / ds.prezzi[i] - 1) * 100 for i, d in enumerate(ds.dates)
               if d > fine_calibrazione and i + 365 < len(ds) and stati[d] == engine.STRAORDINARIO]
        tutti = [(ds.prezzi[i + 365] / ds.prezzi[i] - 1) * 100 for i, d in enumerate(ds.dates)
                 if d > fine_calibrazione and i + 365 < len(ds) and stati[d] != engine.SCONOSCIUTO]
        if fwd:
            print(f"  rendimento a +12 mesi dei giorni straordinari NUOVI: mediana "
                  f"{statistics.median(fwd):+.0f}% ({100*sum(1 for x in fwd if x > 0)/len(fwd):.0f}% "
                  f"positivi) contro {statistics.median(tutti):+.0f}% di un giorno qualsiasi")


if __name__ == "__main__":
    main()
