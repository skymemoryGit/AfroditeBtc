"""Simulazione dello sforzo straordinario: moltiplicatore, tranche e tetto per ciclo (F2.4-F2.5).

    python3 backtest/simula_sforzo.py

Cosa fa: fa girare la regola dei tre stati su tutta la storia e, ogni lunedi', decide se versare
solo il ricorrente o anche una tranche straordinaria. Poi confronta il risultato col DCA puro
**a parita' di depositi** (D1: mai il ROI in euro, sempre i BTC accumulati).

Regole applicate, tutte dichiarate in docs/04 §1.8 prima del test:
- moltiplicatore m = 1 + (M_max - 1) x profondita' normalizzata, arrotondato a 0,5;
- l'extra della settimana vale (m - 1) x budget_mensile / 4: lo sforzo e' spalmato, mai in un colpo;
- il tetto per ciclo e' espresso in MESI EQUIVALENTI di budget, cosi' vale anche se il budget
  passa da 200 a 500 o 1000 euro;
- le bande riservano capienza alle fasi piu' profonde (30 % / 65 % / 100 % del tetto);
- il tetto si azzera quando il prezzo segna un nuovo massimo storico: quel ciclo di accumulo
  ha finito il suo lavoro. E' una regola calcolabile in tempo reale, non una data scelta a mano.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import config
from botbtc import dataset, engine

BUDGET = 200.0            # euro al mese (parametro, non costante di progetto)
FEE = 0.001               # 0,1 %, come nel backtest v5.1
INIZIO = datetime.date(2015, 1, 1)
SOGLIE = None   # le soglie vengono da bot/config.py (parametri_motore), unica fonte di verita'
SCENARI_TETTO = (None, 6.0, 12.0, 18.0)   # None = nessun tetto, per confronto


def prepara():
    ds = dataset.carica_da_csv(serie="coinmetrics")
    dataset.aggiungi_percentili(ds, 1460)
    percentili = [dataset.percentili_del_giorno(ds, i) for i in range(len(ds))]
    parametri = config.parametri_motore()
    righe = engine.serie_stati(percentili, parametri)
    return ds, parametri, righe


def simula(ds, parametri, righe, tetto_mesi):
    """Ritorna il riepilogo della simulazione con un dato tetto (None = illimitato)."""
    btc = 0.0
    depositato = 0.0
    versamenti = []           # (data, euro, prezzo, tipo)
    speso_ciclo = 0.0
    ciclo = 1
    cicli = {}
    massimo_storico = 0.0
    mese_fatto = None
    ultima_settimana = None

    for i, giorno in enumerate(ds.dates):
        if giorno < INIZIO:
            massimo_storico = max(massimo_storico, ds.prezzi[i])
            continue
        prezzo = ds.prezzi[i]

        # nuovo massimo storico: il ciclo di accumulo e' chiuso, il tetto torna pieno
        if prezzo > massimo_storico:
            if speso_ciclo > 0:
                cicli.setdefault(ciclo, {})["chiuso_il"] = giorno
                ciclo += 1
            massimo_storico = prezzo
            speso_ciclo = 0.0

        # versamento ricorrente: il primo giorno di ogni mese
        if mese_fatto != (giorno.year, giorno.month):
            mese_fatto = (giorno.year, giorno.month)
            btc += (BUDGET * (1 - FEE)) / prezzo
            depositato += BUDGET
            versamenti.append((giorno, BUDGET, prezzo, "ricorrente"))

        # decisione di sforzo: una volta a settimana (lunedi')
        if giorno.weekday() != 0 or ultima_settimana == giorno.isocalendar()[:2]:
            continue
        ultima_settimana = giorno.isocalendar()[:2]
        riga = righe[i]
        if riga.get("stato_confermato") != engine.STRAORDINARIO:
            continue
        punteggio = riga["punteggio_economico"]
        m = engine.moltiplicatore(punteggio, parametri) or 1.0
        extra = (m - 1.0) * BUDGET / 4.0
        if extra <= 0:
            continue
        if tetto_mesi is not None:
            disponibile_mesi = engine.tranche_consentita(punteggio, speso_ciclo / BUDGET,
                                                         tetto_mesi, parametri)
            extra = min(extra, max(0.0, disponibile_mesi) * BUDGET)
        if extra < 1.0:
            continue
        btc += (extra * (1 - FEE)) / prezzo
        depositato += extra
        speso_ciclo += extra
        versamenti.append((giorno, extra, prezzo, "straordinario"))
        voce = cicli.setdefault(ciclo, {"speso": 0.0, "settimane": 0, "punteggio_max": 0.0,
                                        "primo": giorno, "prezzi": []})
        voce["speso"] += extra
        voce["settimane"] += 1
        voce["punteggio_max"] = max(voce["punteggio_max"], punteggio)
        voce["prezzi"].append((prezzo, extra))
        voce["ultimo"] = giorno

    # DCA puro a parita' di depositi: stessa somma totale, spalmata su tutti i mesi
    mesi = sorted({(g.year, g.month): (g, p) for g, e, p, t in versamenti
                   if t == "ricorrente"}.items())
    quota_mensile = depositato / len(mesi)
    btc_dca = sum((quota_mensile * (1 - FEE)) / prezzo for _, (_, prezzo) in mesi)

    prezzo_finale = ds.prezzi[-1]
    return {"tetto": tetto_mesi, "btc": btc, "btc_dca": btc_dca, "depositato": depositato,
            "mesi": len(mesi), "versamenti": versamenti, "cicli": cicli,
            "valore": btc * prezzo_finale, "valore_dca": btc_dca * prezzo_finale}


def main():
    ds, parametri, righe = prepara()
    print("=" * 100)
    print(f"SIMULAZIONE DELLO SFORZO — {INIZIO} -> {ds.dates[-1]}, budget {BUDGET:.0f} EUR/mese, fee {FEE*100:.1f}%")
    print("=" * 100)

    risultati = [simula(ds, parametri, righe, tetto) for tetto in SCENARI_TETTO]

    base = simula(ds, parametri, righe, 0.0)     # tetto zero = nessuno sforzo straordinario
    print(f"\n  Riferimento senza bot: solo {BUDGET:.0f} EUR/mese per {base['mesi']} mesi = "
          f"{base['depositato']:,.0f} EUR -> {base['btc']:.4f} BTC")

    print(f"\n{'tetto per ciclo':18} {'depositato':>12} {'BTC':>12} {'BTC col DCA':>12} "
          f"{'differenza':>11} {'extra versati':>14}")
    for r in risultati:
        etichetta = "nessuno" if r["tetto"] is None else f"{r['tetto']:.0f} mesi equivalenti"
        extra = sum(e for _, e, _, t in r["versamenti"] if t == "straordinario")
        diff = (r["btc"] / r["btc_dca"] - 1) * 100
        print(f"  {etichetta:16} {r['depositato']:>11,.0f}E {r['btc']:>12.4f} {r['btc_dca']:>12.4f} "
              f"{diff:>+10.1f}% {extra:>13,.0f}E")
    print("\n  Lettura: la colonna 'differenza' e' il confronto onesto (D1): a PARITA' di depositi, quanto")
    print("  ha aggiunto il TEMPISMO. E' piccola, ed e' coerente con l'analisi v5.1 (il timing vale poco).")
    print("  Il grosso del beneficio non e' il tempismo: e' aver messo piu' soldi nelle fasi economiche.")
    r12_ = [r for r in risultati if r["tetto"] == 12.0][0]
    print(f"  Rispetto al solo ricorrente: {r12_['btc']:.4f} BTC contro {base['btc']:.4f} "
          f"({(r12_['btc']/base['btc']-1)*100:+.1f}%) avendo versato "
          f"{r12_['depositato']-base['depositato']:,.0f} EUR in piu' ({(r12_['depositato']/base['depositato']-1)*100:+.1f}%).")

    print("\n" + "-" * 100)
    print("Dettaglio per ciclo, con il tetto a 12 mesi equivalenti")
    r12 = [r for r in risultati if r["tetto"] == 12.0][0]
    print(f"  {'ciclo':6} {'dal':12} {'al':12} {'settimane':>10} {'speso':>10} {'mesi eq.':>9} "
          f"{'prezzo medio':>13} {'punteggio max':>14} {'capienza residua':>17}")
    for numero, voce in sorted(r12["cicli"].items()):
        if "speso" not in voce:
            continue
        peso = sum(e for _, e in voce["prezzi"])
        prezzo_medio = sum(p * e for p, e in voce["prezzi"]) / peso if peso else 0
        residua = engine.tranche_consentita(voce["punteggio_max"], voce["speso"] / BUDGET, 12.0, parametri)
        print(f"  {numero:^6} {str(voce['primo']):12} {str(voce.get('ultimo','')):12} {voce['settimane']:>10} "
              f"{voce['speso']:>9,.0f}E {voce['speso']/BUDGET:>9.1f} {prezzo_medio:>12,.0f}$ "
              f"{voce['punteggio_max']:>14.2f} {residua:>16.1f} mesi")

    print("\n" + "-" * 100)
    print("Verifiche richieste dal piano")
    ok = []
    # F2.4: mai tutto in un colpo solo. La verifica giusta non e' "almeno 3 tranche per ciclo"
    # (una fase economica puo' durare una settimana sola, come giugno 2026), ma "nessuna tranche
    # si mangia una fetta grossa del tetto".
    tranche = [e for _, e, _, t in r12["versamenti"] if t == "straordinario"]
    massima = max(tranche) if tranche else 0.0
    quota_massima = 100.0 * massima / (12.0 * BUDGET)
    ok.append((f"la tranche piu' grande vale {massima:,.0f}E, cioe' il {quota_massima:.1f}% del tetto "
               f"(richiesto < 10%)", quota_massima < 10.0))
    lunghe = [v for v in r12["cicli"].values() if v.get("settimane", 0) and v["settimane"] >= 3]
    ok.append((f"nelle fasi economiche lunghe lo sforzo e' spalmato: "
               f"{len(lunghe)} cicli su {len([v for v in r12['cicli'].values() if 'settimane' in v])} "
               f"con almeno 3 tranche", bool(lunghe)))
    # F2.4: i 177 giorni sotto la 200-WMA del 2022 non si esauriscono al primo giorno
    versamenti_2022 = [(g, e) for g, e, _, t in r12["versamenti"]
                       if t == "straordinario" and datetime.date(2022, 5, 1) <= g <= datetime.date(2023, 6, 30)]
    totale_2022 = sum(e for _, e in versamenti_2022)
    primo = versamenti_2022[0][1] if versamenti_2022 else 0
    ok.append((f"2022-23: {len(versamenti_2022)} tranche, la prima e' il {primo/totale_2022*100:.0f}% "
               f"del totale del periodo" if totale_2022 else "2022-23: nessuna tranche",
               bool(versamenti_2022) and primo / totale_2022 < 0.25))
    # F2.5: mai oltre il tetto, e capienza ancora disponibile al punto piu' profondo
    sforo = [n for n, v in r12["cicli"].items() if v.get("speso", 0) > 12.0 * BUDGET + 1]
    ok.append(("nessun ciclo supera il tetto di 12 mesi equivalenti", not sforo))
    capienza = []
    for numero, voce in r12["cicli"].items():
        if "punteggio_max" not in voce:
            continue
        residua = engine.tranche_consentita(voce["punteggio_max"], voce["speso"] / BUDGET, 12.0, parametri)
        capienza.append((numero, residua))
    ok.append(("arrivando al punto piu' profondo restava capienza in ogni ciclo "
               f"(minimo {min(r for _, r in capienza):.1f} mesi)" if capienza else "nessun ciclo",
               all(r > 0 for _, r in capienza)))
    for testo, esito in ok:
        print(f"  {'OK ' if esito else 'NO '} {testo}")

    print("\n" + "-" * 100)
    print("Il caso che ha fatto nascere il progetto: giugno 2026")
    for giorno, euro, prezzo, tipo in r12["versamenti"]:
        if tipo == "straordinario" and datetime.date(2026, 6, 1) <= giorno <= datetime.date(2026, 7, 31):
            i = ds.indice(giorno)
            m = engine.moltiplicatore(righe[i]["punteggio_economico"], parametri)
            print(f"  {giorno}: il bot avrebbe detto 'settimana da {m:g}x' -> {euro:,.0f} EUR extra "
                  f"a {prezzo:,.0f} $ (punteggio {righe[i]['punteggio_economico']:.2f})")
    print(f"  Prezzo di oggi ({ds.dates[-1]}): {ds.prezzi[-1]:,.0f} $")
    return 0 if all(e for _, e in ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
