"""
Indicatori per il BOT BTC "report giornaliero" (sessione 03, 2026-09-20).

Solo libreria standard. Nessuna dipendenza esterna, come backtest_v51.py.

Convenzioni:
- Tutte le funzioni lavorano su liste allineate a una lista di date (datetime.date),
  ordinate in modo crescente, un valore per giorno di calendario, senza buchi.
- Ogni indicatore restituisce una lista della stessa lunghezza con None finche'
  non ha abbastanza storia: NESSUN valore e' calcolato guardando avanti nel tempo
  (no lookahead), perche' questi stessi numeri devono poter essere calcolati dal
  bot in tempo reale.
"""

import csv
import datetime
import math
import os

# ---------------------------------------------------------------- caricamento

def load_csv(path, date_col="date", cols=()):
    """Legge un CSV con colonna data + colonne numeriche. Ritorna (dates, {col: [float|None]})."""
    dates, out = [], {c: [] for c in cols}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            dates.append(datetime.date.fromisoformat(row[date_col][:10]))
            for c in cols:
                v = row[c].strip()
                out[c].append(float(v) if v else None)
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    dates = [dates[i] for i in order]
    for c in cols:
        out[c] = [out[c][i] for i in order]
    return dates, out


def check_daily_continuity(dates):
    """Ritorna la lista dei buchi (giorno_prima, giorno_dopo) nella serie giornaliera."""
    return [(dates[i - 1], dates[i]) for i in range(1, len(dates))
            if (dates[i] - dates[i - 1]).days != 1]

# ------------------------------------------------------------------ di base

def sma(values, window):
    out, acc, buf = [], 0.0, []
    for v in values:
        buf.append(v)
        acc += v
        if len(buf) > window:
            acc -= buf.pop(0)
        out.append(acc / window if len(buf) == window else None)
    return out


def mayer_multiple(prices, sma200):
    return [p / s if s else None for p, s in zip(prices, sma200)]


def drawdown_from_max(prices, window=365):
    """Distanza percentuale (negativa) dal massimo degli ultimi `window` giorni, incluso oggi."""
    out = []
    for i, p in enumerate(prices):
        lo = max(0, i - window + 1)
        peak = max(prices[lo:i + 1])
        out.append((p / peak - 1.0) * 100.0)
    return out


def rsi_wilder(values, period=14):
    """RSI di Wilder. Primo valore alla barra `period` (media semplice dei primi `period` delta)."""
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / period, losses / period
    out[period] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return out

# ------------------------------------------------------------- settimanale

def weekly_closes(dates, prices):
    """Chiusure settimanali ISO (settimana lunedi'-domenica): ultimo giorno disponibile di ogni settimana.

    Ritorna (week_end_dates, week_closes, idx_giornaliero -> indice dell'ultima settimana CHIUSA
    a quella data). L'indice serve per evitare lookahead: al giorno t il bot conosce solo le
    settimane gia' concluse (piu', eventualmente, la settimana in corso come valore provvisorio).
    """
    w_end, w_close, key_prev = [], [], None
    for d, p in zip(dates, prices):
        key = d.isocalendar()[:2]
        if key != key_prev:
            w_end.append(d)
            w_close.append(p)
            key_prev = key
        else:
            w_end[-1] = d
            w_close[-1] = p
    return w_end, w_close


def indice_settimana(dates):
    """Per ogni giorno, l'indice della sua settimana ISO nella lista di `weekly_closes`.

    Si ricava dal CALENDARIO, non dalla data di fine settimana: la domenica della settimana in
    corso, a meta' settimana, e' futuro. Una prima versione usava proprio quella data per decidere
    quali settimane fossero chiuse, e cosi' il calcolo sullo storico completo e quello del bot live
    (che vede solo fino a oggi) davano numeri diversi. Trovato il 2026-09-22 con il test di
    troncamento (tests/test_lookahead.py): D41.
    """
    fuori, indice, precedente = [], -1, None
    for d in dates:
        chiave = d.isocalendar()[:2]
        if chiave != precedente:
            indice += 1
            precedente = chiave
        fuori.append(indice)
    return fuori


def weekly_series_to_daily(dates, w_end, w_values, include_current_week=True):
    """Proietta una serie settimanale sui giorni, senza guardare avanti.

    include_current_week=True  -> al giorno t il valore della settimana in corso (provvisorio);
    include_current_week=False -> al giorno t il valore dell'ultima settimana GIA' CHIUSA.
    """
    settimane = indice_settimana(dates)
    out = []
    for k in settimane:
        if include_current_week:
            out.append(w_values[k] if k < len(w_values) else None)
        else:
            out.append(w_values[k - 1] if k >= 1 else None)
    return out


def weekly_rsi_daily(dates, prices, period=14, include_current_week=True):
    """RSI-14 settimanale riportato su base giornaliera, senza lookahead.

    Al giorno t: tutte le settimane gia' chiuse, piu' (se richiesto) la settimana in corso con il
    prezzo di oggi come chiusura provvisoria — cioe' quello che si vede sul grafico settimanale
    in diretta quel giorno, e niente di piu'.
    """
    _, w_close = weekly_closes(dates, prices)
    settimane = indice_settimana(dates)
    out = []
    for i, k in enumerate(settimane):
        closes = w_close[:k] + ([prices[i]] if include_current_week else [])
        out.append(rsi_wilder(closes, period)[-1] if len(closes) > period else None)
    return out


def wma200_daily(dates, prices, weeks=200, include_current_week=True):
    """Media mobile a 200 settimane su base giornaliera, senza lookahead (vedi indice_settimana)."""
    _, w_close = weekly_closes(dates, prices)
    settimane = indice_settimana(dates)
    out = []
    for i, k in enumerate(settimane):
        closes = w_close[:k] + ([prices[i]] if include_current_week else [])
        out.append(sum(closes[-weeks:]) / weeks if len(closes) >= weeks else None)
    return out

# --------------------------------------------------------------- pi cycle

def pi_cycle(prices, fast=111, slow=350, mult=2.0):
    """Pi Cycle Top: 111-DMA vs 2x350-DMA.

    Ritorna (ma111, ma350x2, ratio, cross_up) dove cross_up[i] e' True nel giorno in cui
    la 111-DMA passa sopra il doppio della 350-DMA (il segnale vero e proprio).
    """
    f, s = sma(prices, fast), sma(prices, slow)
    s2 = [x * mult if x is not None else None for x in s]
    ratio = [a / b if (a is not None and b) else None for a, b in zip(f, s2)]
    cross = [False] * len(prices)
    for i in range(1, len(prices)):
        if ratio[i] is not None and ratio[i - 1] is not None:
            cross[i] = ratio[i - 1] < 1.0 <= ratio[i]
    return f, s2, ratio, cross

# ------------------------------------------------------------------- mvrv

def realized_cap(market_cap, mvrv):
    """Realized cap = market cap / MVRV.

    Nel tier community di CoinMetrics `CapRealUSD` risponde 403 (metrica a pagamento),
    ma `CapMrktCurUSD` e `CapMVRVCur` sono gratis: la realized cap si ricava per divisione.
    Verifica fatta il 2026-09-20 (vedi docs/tracking/2026-09-20_sessione-03.md).
    """
    return [mc / m if (mc is not None and m) else None for mc, m in zip(market_cap, mvrv)]


def mvrv_zscore_expanding(market_cap, mvrv, min_days=365):
    """MVRV Z-score "classico": (market cap - realized cap) / deviazione standard della market cap.

    Deviazione standard calcolata su finestra ESPANSIVA (dal primo giorno disponibile fino a
    oggi compreso): e' la definizione usata dalle dashboard pubbliche, ed e' calcolabile in
    tempo reale senza guardare il futuro. Popolazione (ddof=0).
    """
    rc = realized_cap(market_cap, mvrv)
    out, n, s1, s2 = [], 0, 0.0, 0.0
    for mc, r in zip(market_cap, rc):
        n += 1
        s1 += mc
        s2 += mc * mc
        var = max(s2 / n - (s1 / n) ** 2, 0.0)
        sd = math.sqrt(var)
        out.append((mc - r) / sd if (n >= min_days and sd > 0 and r is not None) else None)
    return out


def rolling_zscore(values, window):
    """Z-score rolling di una serie qualunque (usato per lo z-score dell'MVRV su finestra mobile)."""
    out, buf, s1, s2 = [], [], 0.0, 0.0
    for v in values:
        buf.append(v)
        s1 += v
        s2 += v * v
        if len(buf) > window:
            old = buf.pop(0)
            s1 -= old
            s2 -= old * old
        if len(buf) < window:
            out.append(None)
            continue
        n = len(buf)
        var = max(s2 / n - (s1 / n) ** 2, 0.0)
        sd = math.sqrt(var)
        out.append((v - s1 / n) / sd if sd > 0 else None)
    return out


def percentile_rank(values, window):
    """Posizione percentile del valore di oggi dentro la finestra mobile degli ultimi `window` giorni.

    0 = il piu' basso della finestra, 100 = il piu' alto. Usa solo dati passati (niente lookahead).
    Serve perche' le soglie assolute di MVRV (e ancora di piu' quelle dello Z-score) si abbassano
    di ciclo in ciclo: il percentile dice "quanto e' caro rispetto agli ultimi N anni" e resta
    confrontabile tra cicli diversi.
    """
    from bisect import bisect_left
    out = []
    for i, v in enumerate(values):
        if v is None or i + 1 < window:
            out.append(None)
            continue
        w = sorted(values[i - window + 1:i + 1])
        out.append(100.0 * bisect_left(w, v) / (len(w) - 1))
    return out

# --------------------------------------------------------------- bundle
# (il percorso dei dati sta in botbtc/paths.py: unica fonte di verita')


def compute_all(dates, prices, market_cap=None, mvrv=None, fng=None):
    """Calcola tutti gli indicatori del bot di report e li restituisce come dict di liste."""
    s200 = sma(prices, 200)
    ma111, ma350x2, pi_ratio, pi_cross = pi_cycle(prices)
    ind = {
        "sma200": s200,
        "mayer": mayer_multiple(prices, s200),
        "dd365": drawdown_from_max(prices, 365),
        "rsi14_d": rsi_wilder(prices, 14),
        "rsi14_w": weekly_rsi_daily(dates, prices, 14),
        "wma200": wma200_daily(dates, prices),
        "pi_ma111": ma111,
        "pi_ma350x2": ma350x2,
        "pi_ratio": pi_ratio,
        "pi_cross": pi_cross,
    }
    ind["price_vs_wma200"] = [p / w if w else None for p, w in zip(prices, ind["wma200"])]
    if market_cap is not None and mvrv is not None:
        ind["mvrv"] = mvrv
        ind["realized_cap"] = realized_cap(market_cap, mvrv)
        ind["mvrv_z"] = mvrv_zscore_expanding(market_cap, mvrv)
        ind["mvrv_z_4y"] = rolling_zscore(mvrv, 1460)
        ind["mvrv_pct4y"] = percentile_rank(mvrv, 1460)
        ind["mvrv_pct2y"] = percentile_rank(mvrv, 730)
    if fng is not None:
        ind["fng"] = fng
    return ind


def percentile_rank_con_buchi(values, window, minimo=365):
    """Come `percentile_rank`, ma tollera i buchi (None) dentro la finestra.

    Serve agli ingredienti che non esistono per tutta la storia (Fear & Greed dal 2018) o che
    arrivano in ritardo (MVRV a T+1). Il percentile si calcola sui soli valori presenti nella
    finestra, e richiede almeno `minimo` valori: sotto quella soglia restituisce None invece di
    un numero costruito su troppa poca storia.
    """
    from bisect import bisect_left
    out = []
    for i, v in enumerate(values):
        if v is None:
            out.append(None)
            continue
        finestra = [x for x in values[max(0, i - window + 1):i + 1] if x is not None]
        if len(finestra) < minimo:
            out.append(None)
            continue
        finestra.sort()
        out.append(100.0 * bisect_left(finestra, v) / (len(finestra) - 1))
    return out
