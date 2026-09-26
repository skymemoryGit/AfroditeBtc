"""
Backtest engine for BOT BTC v5.1 (pseudo-code in bot_btc_v5_1_buy_sell_maxreturn.docx)
Compares: v5.1 (BUY+SELL), v4 (BUY only), pure DCA.
Data: Coinbase BTC-USD daily closes (2017-01-01 .. 2026-09-17), alternative.me Fear&Greed (2018-02-01 .. 2026-09-18)

Interpretations of ambiguous points in the spec (documented in the analysis):
 I1. Stress/euforia tiers (+50/+30/+10) are EXCLUSIVE (if/elif), not cumulative. `base` is unused.
 I2. Weekly decision every Monday, using Monday's daily indicators (computed on the previous close); orders executed at Monday close, fee 0.1%.
 I3. Trend: >=5 consecutive closes below MA200 -> downtrend; >=5 above -> uptrend; otherwise keep previous.
 I4. "banda_corrente" in the mutual-exclusion rule = the stress band of the PREVIOUS week (as written, PASSO 2 runs before PASSO 3).
 I5. Weekly DCA amount = budget_DCA_rimasto / Mondays remaining in the month (generalises 35 €/week and fixes the 5-Monday overspend).
 I6. Band-3 dip = min(37, sett_dip + 0.4*riserva_dip) (fixes the "riserva_dip=0 -> dip=0" bug).
 I7. Band 0: 15 € moved from budget_dip_rimasto to riserva_dip (no double counting at month end).
 I8. Cumulative sold cap: sold_cycle <= 50% of (stack + sold_cycle); residual sellable = 0.5*(stack+sold_cycle) - sold_cycle.
     Cycle counter resets when riserva_sell is back to 0 and banda_sell == 0.
 I9. carrello_sell is cleared when banda_sell drops to 0.
 I10. Expired riserva_sell -> budget_DCA_rimasto of the current month (spent via I5).
 I11. Missing FNG days are forward-filled.
"""
import csv, datetime as dt, math, sys
from collections import defaultdict

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
from botbtc.paths import DATA

def load_prices():
    px = {}
    with open(DATA + 'btc_close_usd_coinbase.csv') as f:
        r = csv.DictReader(f)
        for row in r:
            px[dt.date.fromisoformat(row['date'])] = float(row['close'])
    return px

def load_fng():
    fng = {}
    with open(DATA + 'fng_alternative_me.csv') as f:
        r = csv.DictReader(f)
        for row in r:
            fng[dt.date.fromisoformat(row['date'])] = int(row['fng'])
    return fng

def rsi_wilder(closes, n=14):
    """closes: list of floats (chronological). returns list of RSI (None until enough data)."""
    out = [None] * len(closes)
    gains = []; losses = []
    avg_g = avg_l = None
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i-1]
        g = max(ch, 0); l = max(-ch, 0)
        if i <= n:
            gains.append(g); losses.append(l)
            if i == n:
                avg_g = sum(gains)/n; avg_l = sum(losses)/n
                out[i] = 100 - 100/(1 + (avg_g/avg_l if avg_l > 0 else float('inf')))
        else:
            avg_g = (avg_g*(n-1) + g)/n
            avg_l = (avg_l*(n-1) + l)/n
            rs = avg_g/avg_l if avg_l > 0 else float('inf')
            out[i] = 100 - 100/(1+rs)
    return out

def build_daily(px, fng):
    dates = sorted(px)
    closes = [px[d] for d in dates]
    rsi = rsi_wilder(closes)
    daily = {}
    # forward fill fng
    last_fng = None
    ma200 = None; s200 = 0.0
    trend = 'grey'; below = 0; above = 0
    rsi_le30 = 0; rsi_ge75 = 0; fng_le20 = 0; fng_ge80 = 0
    for i, d in enumerate(dates):
        c = closes[i]
        s200 += c
        if i >= 200: s200 -= closes[i-200]
        ma = s200/200 if i >= 199 else None
        mx365 = max(closes[max(0, i-364):i+1]) if i >= 364 else None
        f = fng.get(d, last_fng); last_fng = f
        r = rsi[i]
        # streaks
        if ma is not None:
            if c < ma: below += 1; above = 0
            elif c > ma: above += 1; below = 0
            else: below = above = 0
            if below >= 5: trend = 'downtrend'
            elif above >= 5: trend = 'uptrend'
        if r is not None:
            rsi_le30 = rsi_le30 + 1 if r <= 30 else 0
            rsi_ge75 = rsi_ge75 + 1 if r >= 75 else 0
        if f is not None:
            fng_le20 = fng_le20 + 1 if f <= 20 else 0
            fng_ge80 = fng_ge80 + 1 if f >= 80 else 0
        daily[d] = dict(close=c, ma200=ma, max365=mx365, fng=f, rsi=r, trend=trend,
                        below=below, above=above, rsi_le30=rsi_le30, rsi_ge75=rsi_ge75,
                        fng_le20=fng_le20, fng_ge80=fng_ge80)
    return dates, daily

def mondays_in_month(y, m):
    d = dt.date(y, m, 1); out = []
    while d.month == m:
        if d.weekday() == 0: out.append(d)
        d += dt.timedelta(days=1)
    return out

def clip(x, lo=0, hi=100): return max(lo, min(hi, x))

class Engine:
    def __init__(self, cfg, sell_enabled=True, dip_enabled=True, log=None, fng_enabled=True):
        self.cfg = cfg
        self.sell_enabled = sell_enabled
        self.dip_enabled = dip_enabled
        self.fng_enabled = fng_enabled
        self.log = log if log is not None else []
        c = cfg
        # money
        self.budget_dca = 0.0; self.budget_dip = 0.0; self.riserva_dip = 0.0
        self.carrello = 0.0; self.speso = 0.0; self.deposited = 0.0
        # sell side
        self.stack = 0.0; self.sold_cycle = 0.0; self.carrello_sell = 0.0
        self.riserva_sell = 0.0; self.riserva_sell_scad = None
        self.fees = 0.0; self.cost_basis = 0.0  # € spent on BTC currently held (approx pmc)
        # state
        self.banda = 0; self.banda_sell = 0
        self.stress_prev = 0; self.euf_prev = 0
        self.n_buy = 0; self.n_sell = 0
        self.sell_events = []; self.buy_events = []
        self.dca_extra_next = 0.0

    def new_month(self, d):
        c = self.cfg
        self.deposited += c['budget_mese']
        self.budget_dca += c['budget_mese']*c['quota_dca_frac'] + self.dca_extra_next
        self.dca_extra_next = 0.0
        self.budget_dip += c['budget_mese']*(1-c['quota_dca_frac'])

    def end_month(self, d, price):
        c = self.cfg
        # 1. spend ALL remaining DCA budget
        if self.budget_dca > 1e-9:
            self.carrello += self.budget_dca; self.budget_dca = 0.0
            self.execute_buy(d, price, forced=True)
        # 2. unspent dip -> reserve
        self.riserva_dip += self.budget_dip; self.budget_dip = 0.0
        # 3. reserve cap -> future DCA
        if self.riserva_dip > c['riserva_max']:
            surplus = self.riserva_dip - c['riserva_max']
            self.riserva_dip = c['riserva_max']; self.dca_extra_next += surplus

    def execute_buy(self, d, price, forced=False):
        c = self.cfg
        if self.carrello <= 1e-9: return
        if not forced and self.carrello < c['carrello_min']: return
        eur = self.carrello; self.carrello = 0.0
        fee = eur*c['fee']; btc = (eur - fee)/price
        self.stack += btc; self.speso += eur; self.fees += fee; self.cost_basis += eur
        self.n_buy += 1; self.buy_events.append((d, eur, price))

    def execute_sell(self, d, price, btc):
        c = self.cfg
        gross = btc*price; fee = gross*c['fee']
        self.stack -= btc; self.sold_cycle += btc
        self.riserva_sell += gross - fee; self.fees += fee
        self.riserva_sell_scad = d + dt.timedelta(days=c['scadenza_giorni'])
        # cost basis: remove proportionally
        self.cost_basis *= (self.stack/(self.stack+btc)) if (self.stack+btc) > 0 else 0
        self.n_sell += 1; self.sell_events.append((d, btc, price, gross - fee))

    def weekly(self, d, day, mondays_left):
        c = self.cfg
        price = day['close']; ma = day['ma200']; mx = day['max365']
        cheap = (price - ma)/ma
        trend = day['trend']
        dd = (price - mx)/mx if trend == 'downtrend' else 0.0
        # --- STRESS ---
        stress = 0
        if cheap <= -0.20 or dd <= -0.40: stress += 50
        elif cheap <= -0.10 or dd <= -0.25: stress += 30
        elif cheap < 0 or dd <= -0.15: stress += 10
        if day['rsi_le30'] >= 5: stress += 20
        if day['rsi'] >= 70: stress -= 15
        if self.fng_enabled and day['fng'] is not None:
            if day['fng'] > 60 and price > ma: stress = min(stress, 40)
            if day['fng_le20'] >= 5: stress += 15
        stress = clip(stress)
        # --- EUFORIA ---
        euf = 0
        if trend == 'uptrend':
            if cheap >= 0.60: euf += 50
            elif cheap >= 0.35: euf += 30
            elif cheap >= 0.20: euf += 10
            if day['rsi_ge75'] >= 5: euf += 20
            if self.fng_enabled and day['fng_ge80'] >= 5: euf += 15
            if price >= 0.95*mx: euf += 10
            if day['rsi'] <= 50: euf -= 10
        if cheap < c['soglia_attivazione']: euf = 0
        if self.banda >= 1: euf = 0          # I4: previous week's band
        euf = clip(euf)
        # --- BANDS (hysteresis) ---
        b = self.banda
        if stress >= 85: b = 3
        if stress >= 75 and self.stress_prev >= 70: b = max(b, 3)
        if stress >= 65 and self.stress_prev >= 60: b = max(b, 2)
        if stress >= 45 and self.stress_prev >= 40: b = max(b, 1)
        bm = c['banda_morta']
        if b == 3 and stress < 70 - bm: b = 2
        if b == 2 and stress < 60 - bm: b = 1
        if b == 1 and stress < 40 - bm: b = 0
        self.banda = b
        bs = self.banda_sell
        if euf >= 85: bs = 3
        if euf >= 75 and self.euf_prev >= 70: bs = max(bs, 3)
        if euf >= 65 and self.euf_prev >= 60: bs = max(bs, 2)
        if euf >= 45 and self.euf_prev >= 40: bs = max(bs, 1)
        if bs == 3 and euf < 70 - bm: bs = 2
        if bs == 2 and euf < 60 - bm: bs = 1
        if bs == 1 and euf < 40 - bm: bs = 0
        if not self.sell_enabled: bs = 0
        self.banda_sell = bs
        # --- CUSTODE: BUY ---
        dca = min(self.budget_dca, self.budget_dca/mondays_left if mondays_left > 0 else self.budget_dca)
        dca = max(dca, 0.0)
        sett_dip = c['budget_mese']*(1-c['quota_dca_frac'])/4
        dip = 0.0
        if self.dip_enabled:
            if b == 3: ideal = min(c['dip_b3_max'], sett_dip + 0.4*self.riserva_dip)
            elif b == 2: ideal = c['dip_b2']
            elif b == 1: ideal = c['dip_b1']
            else:
                ideal = 0.0
                mv = min(sett_dip, self.budget_dip)
                self.budget_dip -= mv; self.riserva_dip += mv
            dip = min(ideal, self.budget_dip + self.riserva_dip)
            take = min(dip, self.budget_dip); self.budget_dip -= take
            self.riserva_dip -= (dip - take)
            # riserva_sell re-entry with max priority
            if b >= 1 and self.riserva_sell > 0:
                extra = max(0.0, min(self.riserva_sell, c['tetto_singolo'] - dca - dip))
                dip += extra; self.riserva_sell -= extra
                if self.riserva_sell < 1e-9: self.riserva_sell = 0.0; self.riserva_sell_scad = None
        else:
            # v4-without-dip variant is not used; keep money flowing as DCA
            pass
        self.budget_dca -= dca
        self.carrello += dca + dip
        # --- CUSTODE: SELL ---
        sell_btc = 0.0
        if self.sell_enabled and bs >= 1:
            total = self.stack + self.sold_cycle
            residual = max(0.0, c['sell_max_cumulo']*total - self.sold_cycle)
            quota = {1: c['sell_b1'], 2: c['sell_b2'], 3: c['sell_b3']}[bs]
            sell_btc = residual*quota
            self.carrello_sell += sell_btc
        elif bs == 0:
            self.carrello_sell = 0.0   # I9
        # --- AGGREGATION ---
        self.execute_buy(d, price)
        if self.sell_enabled and self.carrello_sell*price >= c['carrello_sell_min']:
            self.execute_sell(d, price, self.carrello_sell); self.carrello_sell = 0.0
        # --- expiry of riserva_sell ---
        if self.riserva_sell > 0 and self.riserva_sell_scad is not None and d > self.riserva_sell_scad:
            self.budget_dca += self.riserva_sell; self.riserva_sell = 0.0; self.riserva_sell_scad = None
        if self.riserva_sell <= 0 and bs == 0: self.sold_cycle = 0.0
        self.stress_prev = stress; self.euf_prev = euf
        self.log.append(dict(date=d, price=price, cheap=cheap, dd=dd, trend=trend, stress=stress, euf=euf,
                             banda=b, banda_sell=bs, dca=dca, dip=dip, sell_btc=sell_btc,
                             stack=self.stack, riserva_sell=self.riserva_sell, riserva_dip=self.riserva_dip,
                             fng=day['fng'], rsi=day['rsi']))

    def value(self, price):
        cash = self.budget_dca + self.budget_dip + self.riserva_dip + self.carrello + self.riserva_sell + self.dca_extra_next
        return self.stack*price + cash, cash

def run(cfg, dates, daily, start, end, sell_enabled, dip_enabled=True, fng_enabled=True):
    eng = Engine(cfg, sell_enabled=sell_enabled, dip_enabled=dip_enabled, fng_enabled=fng_enabled)
    cur_month = None
    for d in dates:
        if d < start or d > end: continue
        day = daily[d]
        if day['ma200'] is None or day['max365'] is None or day['rsi'] is None: continue
        if (d.year, d.month) != cur_month:
            cur_month = (d.year, d.month); eng.new_month(d)
        if d.weekday() == 0:
            ml = [m for m in mondays_in_month(d.year, d.month) if m >= d]
            eng.weekly(d, day, len(ml))
        # end of month: last day of month or last date in range
        nxt = d + dt.timedelta(days=1)
        if nxt.month != d.month or d == end:
            eng.end_month(d, day['close'])
    return eng

def run_dca(cfg, dates, daily, start, end):
    """Pure DCA: budget_mese split equally over the Mondays of each month, fee applied."""
    stack = 0.0; spent = 0.0; fees = 0.0; deposited = 0.0; cur_month = None; n = 0
    for d in dates:
        if d < start or d > end: continue
        if (d.year, d.month) != cur_month:
            cur_month = (d.year, d.month); deposited += cfg['budget_mese']
            mons = [m for m in mondays_in_month(d.year, d.month) if m >= d]
            per = cfg['budget_mese']/len(mons) if mons else 0
        if d.weekday() == 0 and per > 0:
            fee = per*cfg['fee']; stack += (per-fee)/daily[d]['close']; spent += per; fees += fee; n += 1
    return dict(stack=stack, spent=spent, fees=fees, deposited=deposited, n=n)

CFG = dict(budget_mese=200.0, quota_dca_frac=0.70, riserva_max=120.0, tetto_singolo=125.0, carrello_min=80.0,
           banda_morta=5, soglia_attivazione=0.15, fee=0.001, sell_max_cumulo=0.50,
           sell_b1=0.10, sell_b2=0.20, sell_b3=0.30, carrello_sell_min=100.0, scadenza_giorni=120,
           dip_b1=15.0, dip_b2=30.0, dip_b3_max=37.0)

def summarize(name, eng, price, deposited_ref=None):
    val, cash = eng.value(price)
    btc_eq = eng.stack + cash/price
    return dict(name=name, stack=eng.stack, cash=cash, value=val, btc_eq=btc_eq, deposited=eng.deposited,
                spent=eng.speso, fees=eng.fees, n_buy=eng.n_buy, n_sell=eng.n_sell,
                avg_cost=(eng.speso - sum(s[3] for s in eng.sell_events))/eng.stack if eng.stack > 0 else None)

if __name__ == '__main__':
    px = load_prices(); fng = load_fng()
    dates, daily = build_daily(px, fng)
    end = dt.date(2026, 9, 14)  # last Monday with data
    starts = [dt.date(2018,2,5), dt.date(2019,1,7), dt.date(2020,1,6), dt.date(2021,1,4), dt.date(2022,1,3), dt.date(2023,1,2), dt.date(2024,1,1), dt.date(2025,1,6)]
    print(f"Final price {daily[end]['close']:.0f} USD on {end}")
    print()
    hdr = f"{'start':10} {'strategy':8} {'deposited':>9} {'BTC held':>10} {'cash':>8} {'value':>9} {'BTC-eq':>10} {'vs DCA':>8} {'avgcost':>8} {'buys':>4} {'sells':>5}"
    print(hdr)
    rows_out = []
    for st in starts:
        dca = run_dca(CFG, dates, daily, st, end)
        v4 = run(CFG, dates, daily, st, end, sell_enabled=False)
        v5 = run(CFG, dates, daily, st, end, sell_enabled=True)
        p = daily[end]['close']
        dca_btc = dca['stack']
        print(f"{st} {'DCA':8} {dca['deposited']:9.0f} {dca_btc:10.5f} {0:8.0f} {dca_btc*p:9.0f} {dca_btc:10.5f} {'':>8} {dca['spent']/dca_btc:8.0f} {dca['n']:4d} {0:5d}")
        for nm, e in (('v4', v4), ('v5.1', v5)):
            s = summarize(nm, e, p)
            rel = (s['btc_eq']/dca_btc - 1)*100
            print(f"{'':10} {nm:8} {s['deposited']:9.0f} {s['stack']:10.5f} {s['cash']:8.0f} {s['value']:9.0f} {s['btc_eq']:10.5f} {rel:+7.2f}% {s['avg_cost'] or 0:8.0f} {s['n_buy']:4d} {s['n_sell']:5d}")
            rows_out.append((st, nm, s, rel))
        print()
    # detailed sell events for the 2018 run
    v5 = run(CFG, dates, daily, starts[0], end, sell_enabled=True)
    print("SELL events (run from 2018-02):")
    for d, btc, pr, net in v5.sell_events:
        print(f"  {d}  sold {btc:.5f} BTC @ {pr:.0f}  net {net:.0f} USD")
    print("Weeks by stress band:", {b: sum(1 for l in v5.log if l['banda']==b) for b in range(4)})
    print("Weeks by sell band:", {b: sum(1 for l in v5.log if l['banda_sell']==b) for b in range(4)})
    # yearly path for 2018 run: BTC-eq of v4 vs v5 vs DCA at each Jan 1
    print()
    print("Path (start 2018-02): BTC-equivalent at year ends")
    for yr in range(2018, 2027):
        e = dt.date(yr, 12, 31) if yr < 2026 else end
        dca = run_dca(CFG, dates, daily, starts[0], e)
        a = run(CFG, dates, daily, starts[0], e, sell_enabled=False)
        b = run(CFG, dates, daily, starts[0], e, sell_enabled=True)
        p = daily[max(dd for dd in dates if dd <= e)]['close']
        va, ca = a.value(p); vb, cb = b.value(p)
        print(f"  {e}  price {p:7.0f}  DCA {dca['stack']:.5f}  v4 {a.stack+ca/p:.5f} ({(a.stack+ca/p)/dca['stack']-1:+.2%})  v5.1 {b.stack+cb/p:.5f} ({(b.stack+cb/p)/dca['stack']-1:+.2%})  v5 cash {cb:.0f}")
