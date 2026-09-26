"""
Validazione MVRV + nuovi indicatori (sessione 03, 2026-09-20).

Stampa i numeri citati in docs/02_indicatori_bot_report.md.
Dati: data/coinmetrics_btc_mvrv.csv (CoinMetrics Community API, 2010-07-18 -> 2026-09-19).
Nessuna dipendenza esterna.
"""

import datetime
import os
import statistics

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
from botbtc import indicators as ind
from botbtc.paths import DATA_DIR as DATA


def load():
    dates, cols = ind.load_csv(os.path.join(DATA, "coinmetrics_btc_mvrv.csv"),
                               cols=("mvrv", "market_cap_usd", "price_usd"))
    gaps = ind.check_daily_continuity(dates)
    assert not gaps, gaps
    return dates, cols["price_usd"], cols["market_cap_usd"], cols["mvrv"]


def find_cycle_extremes(dates, prices, min_drawdown=0.5, min_gap_days=180):
    """Trova i massimi di ciclo (ATH seguiti da un calo > min_drawdown) e i minimi tra un massimo e il successivo."""
    peaks = []
    ath, ath_i = prices[0], 0
    for i, p in enumerate(prices):
        if p > ath:
            # il precedente ATH e' un massimo di ciclo se nel frattempo il prezzo e' sceso abbastanza
            low = min(prices[ath_i:i + 1])
            if ath_i > 0 and low <= ath * (1 - min_drawdown) and (dates[i] - dates[ath_i]).days >= min_gap_days:
                peaks.append(ath_i)
            ath, ath_i = p, i
    peaks.append(ath_i)  # ultimo massimo assoluto della serie
    troughs = []
    for a, b in zip(peaks, peaks[1:]):
        seg = prices[a:b + 1]
        troughs.append(a + seg.index(min(seg)))
    return peaks, troughs


def fmt(v, nd=2):
    return "n/d" if v is None else f"{v:.{nd}f}"



MODERN_TOPS = ["2017-12-16", "2021-04-13", "2021-11-08", "2025-10-06"]


def stability_table(dates, idx, mvrv, I, peaks, troughs):
    """Quanto sono stabili, da un ciclo all'altro, i valori dell'indicatore ai massimi e ai minimi."""
    print("\n" + "=" * 100)
    print("STABILITA' DELLE SOGLIE: valore dell'indicatore ai massimi/minimi di ciclo")
    print(f"{'data':12} {'tipo':5} {'MVRV':>6} {'Z esp':>6} {'Z 4y':>6} {'pct 4y':>7} {'pct 2y':>7} {'Mayer':>6}")
    for kind, lst in (("TOP", peaks), ("BOT", troughs)):
        for i in lst:
            print(f"{dates[i]!s:12} {kind:5} {fmt(mvrv[i]):>6} {fmt(I['mvrv_z'][i]):>6} {fmt(I['mvrv_z_4y'][i]):>6} "
                  f"{fmt(I['mvrv_pct4y'][i],1):>7} {fmt(I['mvrv_pct2y'][i],1):>7} {fmt(I['mayer'][i]):>6}")
    print("\nCoefficiente di variazione ai 4 massimi dell'era moderna " + ", ".join(MODERN_TOPS))
    print("(piu' basso = soglia che si ripete di ciclo in ciclo; piu' alto = soglia che va ritarata ogni volta)")
    for name, key in (("MVRV grezzo", "mvrv"), ("Z-score espansivo", "mvrv_z"), ("Z-score 4y rolling", "mvrv_z_4y"),
                      ("percentile 4 anni", "mvrv_pct4y"), ("Mayer multiple", "mayer")):
        arr = mvrv if key == "mvrv" else I[key]
        vals = [arr[idx[datetime.date.fromisoformat(d)]] for d in MODERN_TOPS]
        if any(v is None for v in vals):
            continue
        cv = statistics.pstdev(vals) / abs(statistics.mean(vals))
        print(f"   {name:20} {[round(v, 2) for v in vals]}  CV = {cv:.3f}")


def forward_by_percentile(dates, prices, I, start=datetime.date(2017, 1, 1)):
    print("\n" + "=" * 100)
    print("RENDIMENTO A +365 GIORNI PER PERCENTILE MVRV SU 4 ANNI (dal 2017)")
    print(f"{'percentile':12} {'giorni':>7} {'mediana':>9} {'positivi':>9} {'peggiore':>9} {'migliore':>9}")
    for lo, hi in ((0, 10), (10, 25), (25, 50), (50, 75), (75, 90), (90, 101)):
        rets = [(prices[i + 365] / prices[i] - 1) * 100 for i in range(len(dates) - 365)
                if I["mvrv_pct4y"][i] is not None and lo <= I["mvrv_pct4y"][i] < hi and dates[i] >= start]
        if not rets:
            continue
        pos = 100 * sum(1 for r in rets if r > 0) / len(rets)
        print(f"{f'{lo}-{hi}':12} {len(rets):>7} {statistics.median(rets):>8.0f}% {pos:>8.0f}% "
              f"{min(rets):>8.0f}% {max(rets):>8.0f}%")


def mvrv_adds_to_mayer(dates, prices, mvrv, I, start=datetime.date(2017, 1, 1)):
    """MVRV e Mayer sono correlati: questa e' la prova che MVRV aggiunge comunque informazione."""
    print("\n" + "=" * 100)
    print("MVRV AGGIUNGE QUALCOSA RISPETTO AL MAYER MULTIPLE?")
    pairs = [(m, y) for d, m, y in zip(dates, mvrv, I["mayer"]) if y is not None and d >= start]
    ax, ay = statistics.mean([p[0] for p in pairs]), statistics.mean([p[1] for p in pairs])
    cov = sum((a - ax) * (b - ay) for a, b in pairs) / len(pairs)
    r = cov / (statistics.pstdev([p[0] for p in pairs]) * statistics.pstdev([p[1] for p in pairs]))
    print(f"  correlazione MVRV/Mayer dal 2017: r = {r:.3f} su {len(pairs)} giorni (molto correlati, ma non identici)")
    print("  dentro ogni banda di Mayer, spacco i giorni in MVRV sotto/sopra la mediana della banda:")
    print(f"  {'banda Mayer':14} {'giorni':>7} {'MVRV mediano':>13} {'+1y con MVRV basso':>20} {'+1y con MVRV alto':>19}")
    for lo, hi in ((0, 0.8), (0.8, 1.0), (1.0, 1.2), (1.2, 1.5), (1.5, 2.4)):
        sel = [i for i in range(len(dates) - 365)
               if dates[i] >= start and I["mayer"][i] is not None and lo <= I["mayer"][i] < hi]
        if len(sel) < 60:
            continue
        med = statistics.median([mvrv[i] for i in sel])
        low = [(prices[i + 365] / prices[i] - 1) * 100 for i in sel if mvrv[i] < med]
        high = [(prices[i + 365] / prices[i] - 1) * 100 for i in sel if mvrv[i] >= med]
        print(f"  {f'{lo}-{hi}':14} {len(sel):>7} {med:>13.2f} "
              f"{statistics.median(low):>18.0f}% {statistics.median(high):>18.0f}%")


def pi_cycle_reach(dates, I):
    print("\n" + "=" * 100)
    print("PI CYCLE: quanto si e' avvicinato al segnale in ogni finestra (rapporto 111-DMA / 2x350-DMA, segnale a 1.00)")
    for a, b in (("2014-01-01", "2018-06-30"), ("2018-07-01", "2021-12-31"), ("2022-01-01", "2026-09-19")):
        seg = [(d, v) for d, v in zip(dates, I["pi_ratio"])
               if v is not None and datetime.date.fromisoformat(a) <= d <= datetime.date.fromisoformat(b)]
        d, v = max(seg, key=lambda x: x[1])
        print(f"  {a} -> {b}: massimo {v:.3f} il {d}")


def main():
    dates, prices, mcap, mvrv = load()
    I = ind.compute_all(dates, prices, market_cap=mcap, mvrv=mvrv)
    idx = {d: i for i, d in enumerate(dates)}

    print("=" * 100)
    print("SERIE:", dates[0], "->", dates[-1], f"({len(dates)} giorni, 0 buchi)")
    print("MVRV oggi:", fmt(mvrv[-1], 3), "| Z-score espansivo:", fmt(I["mvrv_z"][-1], 2),
          "| Z 4 anni rolling:", fmt(I["mvrv_z_4y"][-1], 2))

    peaks, troughs = find_cycle_extremes(dates, prices)
    print("\n" + "=" * 100)
    print("MASSIMI E MINIMI DI CICLO (trovati dai dati, non inseriti a mano)")
    hdr = f"{'tipo':7} {'data':11} {'prezzo':>11} {'MVRV':>6} {'Z esp.':>7} {'Z 4y':>6} {'RSI-W':>6} {'Mayer':>6} {'P/200WMA':>9} {'PiRatio':>8}"
    print(hdr)
    rows = [("TOP", i) for i in peaks] + [("BOTTOM", i) for i in troughs]
    rows.sort(key=lambda r: r[1])
    for kind, i in rows:
        print(f"{kind:7} {dates[i]!s:11} {prices[i]:>11,.0f} {fmt(mvrv[i],2):>6} {fmt(I['mvrv_z'][i]):>7} "
              f"{fmt(I['mvrv_z_4y'][i]):>6} {fmt(I['rsi14_w'][i],1):>6} {fmt(I['mayer'][i]):>6} "
              f"{fmt(I['price_vs_wma200'][i]):>9} {fmt(I['pi_ratio'][i]):>8}")

    print("\n" + "=" * 100)
    print("DERIVA DELLE SOGLIE TRA CICLI (massimo/minimo raggiunto in ogni finestra di ciclo)")
    bounds = [0] + peaks
    print(f"{'finestra':25} {'MVRV max':>9} {'Z esp max':>10} {'Z4y max':>8} {'MVRV min':>9} {'Z esp min':>10} {'Z4y min':>8}")
    for a, b in zip(bounds, bounds[1:]):
        seg = slice(a, b + 1)
        def mm(key, f):
            vals = [v for v in I[key][seg] if v is not None]
            return f(vals) if vals else None
        mv = [v for v in mvrv[seg] if v is not None]
        print(f"{str(dates[a])+' -> '+str(dates[b]):25} {fmt(max(mv)):>9} {fmt(mm('mvrv_z',max)):>10} "
              f"{fmt(mm('mvrv_z_4y',max)):>8} {fmt(min(mv)):>9} {fmt(mm('mvrv_z',min)):>10} {fmt(mm('mvrv_z_4y',min)):>8}")

    print("\n" + "=" * 100)
    print("RENDIMENTO FUTURO A 365 GIORNI PER BANDA DI MVRV (solo giorni con 365 gg di futuro disponibili)")
    for label, start in (("storia completa 2010->", dates[0]), ("solo 2017->", datetime.date(2017, 1, 1))):
        bands = [(0, 1), (1, 1.5), (1.5, 2), (2, 2.5), (2.5, 3.5), (3.5, 99)]
        print(f"\n-- {label}")
        print(f"{'banda MVRV':14} {'giorni':>7} {'mediana +1y':>12} {'media +1y':>10} {'peggiore':>9} {'migliore':>9} {'% positivi':>11}")
        for lo, hi in bands:
            rets = []
            for i, d in enumerate(dates):
                if d < start or i + 365 >= len(dates) or mvrv[i] is None:
                    continue
                if lo <= mvrv[i] < hi:
                    rets.append((prices[i + 365] / prices[i] - 1) * 100)
            if not rets:
                print(f"{f'{lo}-{hi}':14} {0:>7}")
                continue
            pos = 100 * sum(1 for r in rets if r > 0) / len(rets)
            print(f"{f'{lo}-{hi}':14} {len(rets):>7} {statistics.median(rets):>11.0f}% {statistics.mean(rets):>9.0f}% "
                  f"{min(rets):>8.0f}% {max(rets):>8.0f}% {pos:>10.0f}%")

    print("\n" + "=" * 100)
    print("STESSA COSA CON LO Z-SCORE ESPANSIVO (bande classiche delle dashboard)")
    zb = [(-99, 0), (0, 1), (1, 2), (2, 3), (3, 5), (5, 99)]
    print(f"{'banda Z':14} {'giorni':>7} {'mediana +1y':>12} {'media +1y':>10} {'peggiore':>9} {'migliore':>9} {'% positivi':>11}")
    for lo, hi in zb:
        rets = []
        for i in range(len(dates) - 365):
            z = I["mvrv_z"][i]
            if z is None or dates[i] < datetime.date(2017, 1, 1):
                continue
            if lo <= z < hi:
                rets.append((prices[i + 365] / prices[i] - 1) * 100)
        if not rets:
            print(f"{f'{lo}-{hi}':14} {0:>7}")
            continue
        pos = 100 * sum(1 for r in rets if r > 0) / len(rets)
        print(f"{f'{lo}-{hi}':14} {len(rets):>7} {statistics.median(rets):>11.0f}% {statistics.mean(rets):>9.0f}% "
              f"{min(rets):>8.0f}% {max(rets):>8.0f}% {pos:>10.0f}%")

    print("\n" + "=" * 100)
    print("PI CYCLE TOP: incroci 111-DMA sopra 2x350-DMA")
    for i, c in enumerate(I["pi_cross"]):
        if c:
            nxt = [p for p in peaks if p >= i]
            top = nxt[0] if nxt else None
            extra = ""
            if top is not None:
                extra = (f"  -> massimo di ciclo successivo {dates[top]} "
                         f"({(dates[top]-dates[i]).days} gg dopo, prezzo {prices[top]:,.0f} = "
                         f"{(prices[top]/prices[i]-1)*100:+.0f}% rispetto al segnale)")
            print(f"  {dates[i]}  prezzo {prices[i]:>10,.0f}{extra}")

    print("\n" + "=" * 100)
    print("200-WMA: quanto spesso il prezzo ci sta sotto e quanto va sotto")
    below = [(d, p / w - 1) for d, p, w in zip(dates, prices, I["wma200"]) if w]
    under = [x for x in below if x[1] < 0]
    print(f"  giorni con 200-WMA disponibile: {len(below)}  |  giorni sotto: {len(under)} ({100*len(under)/len(below):.1f}%)")
    if under:
        worst = min(under, key=lambda x: x[1])
        print(f"  massimo sfondamento: {worst[0]} a {worst[1]*100:.0f}% sotto la 200-WMA")
        per_year = {}
        for d, r in under:
            per_year.setdefault(d.year, []).append(r)
        print("  anni con prezzo sotto la 200-WMA: " +
              ", ".join(f"{y} ({len(v)} gg, min {min(v)*100:.0f}%)" for y, v in sorted(per_year.items())))

    stability_table(dates, idx, mvrv, I, peaks, troughs)
    forward_by_percentile(dates, prices, I)
    mvrv_adds_to_mayer(dates, prices, mvrv, I)
    pi_cycle_reach(dates, I)

    print("\n" + "=" * 100)
    print("FOTOGRAFIA DI OGGI (" + str(dates[-1]) + ")")
    last = -1
    print(f"  prezzo (CoinMetrics PriceUSD): {prices[last]:,.0f} USD")
    for k, nd in (("mayer", 2), ("dd365", 1), ("rsi14_d", 1), ("rsi14_w", 1),
                  ("price_vs_wma200", 2), ("pi_ratio", 2), ("mvrv", 3), ("mvrv_z", 2), ("mvrv_z_4y", 2),
                  ("mvrv_pct4y", 1), ("mvrv_pct2y", 1)):
        print(f"  {k:16} {fmt(I[k][last], nd)}")
    print(f"  realized cap: {I['realized_cap'][last]:,.0f} USD  |  market cap: {mcap[last]:,.0f} USD")


if __name__ == "__main__":
    main()
