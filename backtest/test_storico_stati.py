"""Test di accettazione storico della regola dei tre stati (F2.3 del piano).

    python3 backtest/test_storico_stati.py

Regola procedurale (docs/03 §F2.3, docs/04 §1): i parametri sono stati scritti PRIMA di questo
test, in `docs/04_regola_stati.md` §1. Qui si guarda solo il risultato. Le soglie non si
scelgono sulle date: si calibrano unicamente sulla quota di giorni accesi (criterio (c)).

Dati: `data/coinmetrics_btc_mvrv.csv` (serie PriceUSD dal 2010 + MVRV) e
`data/fng_alternative_me.csv`. Serve la storia lunga perche' il percentile a 4 anni richiede
quattro anni di passato: partendo dal 2017 non si potrebbero giudicare ne' il 2018 ne' il 2020.
"""

import datetime
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from botbtc import dataset, engine

# --- fatti storici usati come banco di prova (fonte: docs/02 §2, trovati dai dati)
MASSIMI_MODERNI = [datetime.date(2017, 12, 16), datetime.date(2021, 4, 13),
                   datetime.date(2021, 11, 8), datetime.date(2025, 10, 6)]
CASI_ECONOMICI = {"dicembre 2018": (datetime.date(2018, 12, 1), datetime.date(2018, 12, 31)),
                  "marzo 2020": (datetime.date(2020, 3, 1), datetime.date(2020, 3, 31)),
                  "novembre 2022": (datetime.date(2022, 11, 1), datetime.date(2022, 11, 30)),
                  "giugno 2026": (datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))}
INIZIO_RIALZO_2020 = (datetime.date(2020, 11, 1), datetime.date(2020, 12, 31))


def quantile(valori, q):
    """Quantile semplice su lista gia' ordinata di lunghezza n (interpolazione lineare)."""
    if not valori:
        return None
    pos = q * (len(valori) - 1)
    basso, alto = int(pos), min(int(pos) + 1, len(valori) - 1)
    return valori[basso] + (valori[alto] - valori[basso]) * (pos - basso)


def prepara(finestra):
    ds = dataset.carica_da_csv(serie="coinmetrics")
    dataset.aggiungi_percentili(ds, finestra=finestra)
    percentili = [dataset.percentili_del_giorno(ds, i) for i in range(len(ds))]
    return ds, percentili


DURATA_MINIMA_CARO = 60          # giro 2, dichiarato prima di rilanciare: un trimestre


def calibra(percentili, obiettivo_straordinario=0.12, obiettivo_freno=0.20,
            durata_minima_caro=DURATA_MINIMA_CARO):
    """Sceglie le due soglie SOLO sulla quota di giorni (docs/04 §1.6)."""
    base = engine.Parametri(durata_minima_caro=durata_minima_caro)
    eco, caro = [], []
    for pct in percentili:
        r = engine.valuta(pct, base)
        if r["punteggio_economico"] is None:
            continue
        eco.append(r["punteggio_economico"])
        caro.append(r["punteggio_caro"])
    eco.sort()
    caro.sort()
    return (base.copia(soglia_straordinario=round(quantile(eco, 1 - obiettivo_straordinario), 4),
                       soglia_freno=round(quantile(caro, 1 - obiettivo_freno), 4)),
            len(eco))


def esegui(ds, percentili, parametri):
    valori = [{k: ds.ind.get(k, [None] * len(ds))[i] for k in engine.PESI} for i in range(len(ds))]
    righe = engine.serie_stati(percentili, parametri, valori)
    stati = {ds.dates[i]: righe[i]["stato_confermato"] for i in range(len(ds))
             if "stato_confermato" in righe[i]}
    return righe, stati


def quota(stati, stato):
    validi = [s for s in stati.values() if s != engine.SCONOSCIUTO]
    if not validi:
        return 0.0
    return 100.0 * sum(1 for s in validi if s == stato) / len(validi)


def acceso_in(stati, da, a, stato):
    return [g for g, s in stati.items() if da <= g <= a and s == stato]


def rendimenti_futuri(ds, stati, stato, giorni):
    """Rendimento a +`giorni` dei giorni in un certo stato: serve a dire se lo stato informa o no."""
    fuori = []
    for i, g in enumerate(ds.dates):
        if stati.get(g) == stato and i + giorni < len(ds):
            fuori.append((ds.prezzi[i + giorni] / ds.prezzi[i] - 1) * 100)
    return fuori


def prova_incompatibilita(ds, percentili, parametri):
    """Mostra coi numeri perche' (e) ed (f) non possono valere insieme.

    A dicembre 2020 — inizio del rialzo che portera' a 60 mila — il mercato era piu' caro, su
    OGNI ingrediente, di quanto lo fosse ai massimi del 2021-11 e del 2025-10. Qualunque soglia
    sul livello che si accende prima di quei massimi si accende anche li'.
    """
    senza_durata = parametri.copia(durata_minima_caro=0)
    def punteggio(giorno):
        i = ds.indice(giorno)
        return engine.valuta(percentili[i], senza_durata)["punteggio_caro"], i

    print("\n  PROVA DELL'INCOMPATIBILITA' (punteggio 'caro' senza requisito di durata):")
    print(f"    {'data':12} {'prezzo':>10} {'caro':>6} {'MVRV':>6} {'Mayer':>6} {'RSI-W':>6}")
    for giorno, etichetta in [(datetime.date(2020, 12, 15), "inizio rialzo"),
                              (datetime.date(2020, 12, 31), "inizio rialzo"),
                              (datetime.date(2021, 11, 8), "MASSIMO"),
                              (datetime.date(2025, 10, 6), "MASSIMO")]:
        p_caro, i = punteggio(giorno)
        print(f"    {str(giorno):12} {ds.prezzi[i]:>10,.0f} {p_caro:>6.3f} {ds.ind['mvrv'][i]:>6.2f} "
              f"{ds.ind['mayer'][i]:>6.2f} {ds.ind['rsi14_w'][i]:>6.1f}   {etichetta}")
    print("    -> dicembre 2020 e' PIU' caro dei due massimi piu' recenti: nessuna soglia sul livello")
    print("       puo' accendersi a quei massimi e restare spenta li'. Da qui il requisito di durata.")


def confronto_logiche(ds, percentili, parametri):
    """F2.2-bis: AND stretto, OR largo e punteggio a confronto, coi numeri.

    Il piano chiede esplicitamente di giustificare la scelta con una tabella, non a intuito:
    e' il punto in cui il motore puo' fallire in silenzio.
    """
    print("\n" + "-" * 100)
    print("F2.2-bis — le tre logiche di combinazione a confronto")
    logiche = [
        ("AND stretto (tutti)", lambda pct: engine.stato_con_and(pct, parametri)),
        ("AND morbido (5 su 7)", lambda pct: engine.stato_con_and(pct, parametri, quanti_minimo=5)),
        ("OR largo (almeno 1)", lambda pct: engine.stato_con_or(pct, parametri)),
    ]
    print(f"  {'logica':24} {'straord.':>9} {'freno':>8} {'giugno 2026':>13} {'+12 mesi (mediana)':>20} {'positivi':>9}")
    for nome, funzione in logiche:
        stati = {}
        for i, pct in enumerate(percentili):
            st = funzione(pct)
            if st != engine.SCONOSCIUTO:
                stati[ds.dates[i]] = st
        fwd = rendimenti_futuri(ds, stati, engine.STRAORDINARIO, 365)
        mediana = statistics.median(fwd) if fwd else float("nan")
        positivi = 100 * sum(1 for x in fwd if x > 0) / len(fwd) if fwd else float("nan")
        giugno = "acceso" if acceso_in(stati, *CASI_ECONOMICI["giugno 2026"], engine.STRAORDINARIO) else "NO"
        print(f"  {nome:24} {quota(stati, engine.STRAORDINARIO):8.1f}% {quota(stati, engine.FRENO):7.1f}% "
              f"{giugno:>13} {mediana:>19.0f}% {positivi:>8.0f}%")

    # la logica scelta, con la conferma e il requisito di durata gia' applicati
    _, stati = esegui(ds, percentili, parametri)
    fwd = rendimenti_futuri(ds, stati, engine.STRAORDINARIO, 365)
    giugno = "acceso" if acceso_in(stati, *CASI_ECONOMICI["giugno 2026"], engine.STRAORDINARIO) else "NO"
    print(f"  {'PUNTEGGIO (scelta)':24} {quota(stati, engine.STRAORDINARIO):8.1f}% {quota(stati, engine.FRENO):7.1f}% "
          f"{giugno:>13} {statistics.median(fwd):>19.0f}% "
          f"{100*sum(1 for x in fwd if x > 0)/len(fwd):>8.0f}%")
    print("  Lettura: l'AND stretto non si accende quasi mai (basta un ingrediente fuori posto),")
    print("  l'OR largo si accende troppo e perde qualita'. Il punteggio sta in mezzo per costruzione.")


def main():
    print("=" * 100)
    print("TEST DI ACCETTAZIONE DELLA REGOLA DEI TRE STATI — parametri fissati in docs/04 §1")
    print("=" * 100)

    ds, percentili = prepara(1460)
    parametri, giorni_validi = calibra(percentili)
    righe, stati = esegui(ds, percentili, parametri)

    primo_valido = min((g for g, s in stati.items() if s != engine.SCONOSCIUTO), default=None)
    print(f"\nSerie: {ds.dates[0]} -> {ds.dates[-1]} ({len(ds)} giorni), fonte {ds.fonte_prezzo}")
    print(f"Giorni con punteggio calcolabile: {giorni_validi} (dal {primo_valido})")
    print(f"Soglie calibrate solo sulla quota di giorni: straordinario >= {parametri.soglia_straordinario}, "
          f"freno >= {parametri.soglia_freno}")
    print(f"Conferma richiesta: {parametri.conferma_giorni} giorni consecutivi · "
          f"freno solo dopo {parametri.durata_minima_caro} giorni consecutivi sopra la soglia (giro 2)")

    q_str, q_fre = quota(stati, engine.STRAORDINARIO), quota(stati, engine.FRENO)
    print(f"\nQuota di giorni dopo la conferma: straordinario {q_str:.1f}% · "
          f"normale {quota(stati, engine.NORMALE):.1f}% · freno {q_fre:.1f}%")

    esiti = []

    # --- (a) e (b): i casi economici
    print("\n" + "-" * 100)
    print("(a) e (b) — le fasi economiche devono accendersi")
    for nome, (da, a) in CASI_ECONOMICI.items():
        giorni = acceso_in(stati, da, a, engine.STRAORDINARIO)
        ok = bool(giorni)
        esiti.append((f"({'a' if nome == 'giugno 2026' else 'b'}) {nome}", ok))
        dettaglio = f"{len(giorni)} giorni accesi, dal {min(giorni)} al {max(giorni)}" if giorni else "MAI acceso"
        print(f"  {'OK ' if ok else 'NO '} {nome:16} {dettaglio}")

    # --- (c) quota straordinario
    ok_c = 5.0 <= q_str <= 15.0
    esiti.append(("(c) quota straordinario 10-15%", 10.0 <= q_str <= 15.0))
    print("\n" + "-" * 100)
    print(f"(c) — quota dello stato straordinario: {q_str:.1f}% "
          f"({'dentro' if 10 <= q_str <= 15 else 'FUORI'} dall'intervallo 10-15% del piano)")

    # --- (d) niente straordinario nei 3 mesi prima di un massimo
    print("\n" + "-" * 100)
    print("(d) — nessun giorno straordinario nei 3 mesi prima di un massimo di ciclo")
    ok_d = True
    for massimo in MASSIMI_MODERNI:
        da = massimo - datetime.timedelta(days=90)
        giorni = acceso_in(stati, da, massimo, engine.STRAORDINARIO)
        if giorni:
            ok_d = False
        print(f"  {'OK ' if not giorni else 'NO '} massimo {massimo}: {len(giorni)} giorni straordinari nei 90 giorni prima")
    esiti.append(("(d) niente straordinario prima dei massimi", ok_d))

    # --- (e) e (f): i criteri originali del piano, tenuti a vista anche se incompatibili
    print("\n" + "-" * 100)
    print("(e) e (f) ORIGINALI — sono risultati INCOMPATIBILI fra loro: la prova qui sotto")
    colti = 0
    for massimo in MASSIMI_MODERNI:
        da = massimo - datetime.timedelta(days=90)
        giorni = acceso_in(stati, da, massimo, engine.FRENO)
        if giorni:
            colti += 1
        print(f"  {'acceso ' if giorni else 'spento '} massimo {massimo}: {len(giorni)} giorni di freno nei 90 giorni prima")
    giorni_2020 = acceso_in(stati, *INIZIO_RIALZO_2020, engine.FRENO)
    print(f"  massimi colti: {colti}/4 (il criterio (e) ne chiedeva 3)")
    print(f"  novembre-dicembre 2020: {len(giorni_2020)} giorni di freno (il criterio (f) ne chiedeva 0)")
    esiti.append(("(e) ORIGINALE: freno vicino ad almeno 3 massimi su 4", colti >= 3))
    esiti.append(("(f) ORIGINALE: zero freno a inizio rialzo 2020", not giorni_2020))

    prova_incompatibilita(ds, percentili, parametri)

    # --- (e') e (f'): criteri riscritti dopo la prova, approvati dall'utente il 2026-09-20
    print("\n" + "-" * 100)
    print("(e') e (f') RISCRITTI — il freno non deve 'prendere i massimi' ma essere raro e informativo")
    quota_freno = quota(stati, engine.FRENO)
    giorni_freno = [g for g, st in stati.items() if st == engine.FRENO]
    vicini = sum(1 for g in giorni_freno if any(0 <= (m - g).days <= 365 for m in MASSIMI_MODERNI))
    percentuale_vicini = 100.0 * vicini / len(giorni_freno) if giorni_freno else 0.0
    fwd = rendimenti_futuri(ds, stati, engine.FRENO, 365)
    mediana = statistics.median(fwd) if fwd else None
    print(f"  quota di giorni in freno: {quota_freno:.1f}% (richiesto: raro, <= 10%)")
    print(f"  quota dei giorni di freno che cadono entro 12 mesi da un massimo: {percentuale_vicini:.0f}% (richiesto >= 60%)")
    print(f"  rendimento a +12 mesi dei giorni di freno: mediana {mediana:+.0f}% "
          f"({100*sum(1 for x in fwd if x > 0)/len(fwd):.0f}% positivi) — richiesto: mediana negativa")
    print(f"  giorni di freno in nov-dic 2020: {len(giorni_2020)} (tollerati <= 5, solo su estremi dichiarati)")
    if giorni_2020:
        i0 = ds.indice(min(giorni_2020))
        print(f"    il primo e' il {min(giorni_2020)}: MVRV {ds.ind['mvrv'][i0]:.2f}, "
              f"Mayer {ds.ind['mayer'][i0]:.2f}, RSI settimanale {ds.ind['rsi14_w'][i0]:.0f}")
    esiti.append(("(e') freno raro e informativo", quota_freno <= 10.0 and percentuale_vicini >= 60.0
                  and mediana is not None and mediana < 0))
    esiti.append(("(f') freno quasi muto a inizio rialzo 2020", len(giorni_2020) <= 5))

    # --- (g) sensibilita' alla finestra
    print("\n" + "-" * 100)
    print("(g) — sensibilita' alla finestra del percentile. Perimetro dichiarato: 3, 4 e 5 anni.")
    print("      La finestra di 2 anni e' piu' corta di un ciclo di mercato ed e' mostrata solo per informazione.")
    print(f"  {'finestra':10} {'soglie':20} {'straord.':>9} {'freno':>7}   " +
          "  ".join(f"{n:>14}" for n in CASI_ECONOMICI))
    riferimento = stati
    cambi_max, coerenti = 0.0, True
    for finestra in dataset.FINESTRE_PERCENTILE:
        if finestra == 1460:
            st, par = stati, parametri
        else:
            ds_f, pct_f = prepara(finestra)
            par, _ = calibra(pct_f)
            _, st = esegui(ds_f, pct_f, par)
        casi = []
        for nome, (da, a) in CASI_ECONOMICI.items():
            casi.append("acceso" if acceso_in(st, da, a, engine.STRAORDINARIO) else "NO")
        comuni = [g for g in st if g in riferimento
                  and st[g] != engine.SCONOSCIUTO and riferimento[g] != engine.SCONOSCIUTO]
        cambi = 100.0 * sum(1 for g in comuni if st[g] != riferimento[g]) / len(comuni) if comuni else 0.0
        nel_perimetro = finestra >= 1095
        if finestra != 1460 and nel_perimetro:
            cambi_max = max(cambi_max, cambi)
            coerenti = coerenti and all(c == "acceso" for c in casi)
        nota = "(riferimento)" if finestra == 1460 else (f"cambi vs 4 anni: {cambi:.1f}%"
                                                        + ("" if nel_perimetro else "  [fuori perimetro]"))
        print(f"  {finestra:4} gg   {par.soglia_straordinario:.3f}/{par.soglia_freno:.3f}       "
              f"{quota(st, engine.STRAORDINARIO):8.1f}% {quota(st, engine.FRENO):6.1f}%   " +
              "  ".join(f"{c:>14}" for c in casi) + f"   {nota}")
    esiti.append(("(g) stabile a 3, 4 e 5 anni (cambi < 15%, stesse date accese)",
                  cambi_max < 15.0 and coerenti))

    confronto_logiche(ds, percentili, parametri)

    # --- riepilogo
    print("\n" + "=" * 100)
    print("ESITO")
    operativi = [(n, ok) for n, ok in esiti if "ORIGINALE" not in n]
    storici = [(n, ok) for n, ok in esiti if "ORIGINALE" in n]
    for nome, ok in operativi:
        print(f"  {'PASSA ' if ok else 'FALLISCE'} {nome}")
    passati = sum(1 for _, ok in operativi if ok)
    print(f"\n  {passati}/{len(operativi)} criteri operativi superati")
    print("\n  Criteri originali del piano, sostituiti dopo la prova di incompatibilita'")
    print("  (decisione dell'utente del 2026-09-20, motivazione in docs/04 §3):")
    for nome, ok in storici:
        print(f"    {'passava' if ok else 'non passava'}: {nome}")
    return 0 if passati == len(operativi) else 1


if __name__ == "__main__":
    raise SystemExit(main())
