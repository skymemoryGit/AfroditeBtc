import datetime as dt, copy
import backtest_v51 as B

class EngineV(B.Engine):
    """Variants of the SELL module to diagnose what causes the loss."""
    def __init__(self, cfg, variant, **kw):
        super().__init__(cfg, **kw); self.variant = variant

    def weekly(self, d, day, mondays_left):
        v = self.variant
        c = self.cfg
        # temporarily hijack parameters
        if 'target' in v or 'gate' in v:
            return self.weekly_custom(d, day, mondays_left)
        return super().weekly(d, day, mondays_left)

    def weekly_custom(self, d, day, mondays_left):
        # copy of Engine.weekly with modifications flagged by self.variant
        v = self.variant; c = self.cfg
        price = day['close']; ma = day['ma200']; mx = day['max365']
        cheap = (price - ma)/ma; trend = day['trend']
        dd = (price - mx)/mx if trend == 'downtrend' else 0.0
        stress = 0
        if cheap <= -0.20 or dd <= -0.40: stress += 50
        elif cheap <= -0.10 or dd <= -0.25: stress += 30
        elif cheap < 0 or dd <= -0.15: stress += 10
        if day['rsi_le30'] >= 5: stress += 20
        if day['rsi'] >= 70: stress -= 15
        if day['fng'] is not None:
            if day['fng'] > 60 and price > ma: stress = min(stress, 40)
            if day['fng_le20'] >= 5: stress += 15
        stress = B.clip(stress)
        t1, t2, t3 = (0.50, 0.80, 1.20) if 'gate' in v else (0.20, 0.35, 0.60)
        euf = 0
        if trend == 'uptrend':
            if cheap >= t3: euf += 50
            elif cheap >= t2: euf += 30
            elif cheap >= t1: euf += 10
            if day['rsi_ge75'] >= 5: euf += 20
            if day['fng_ge80'] >= 5: euf += 15
            if price >= 0.95*mx: euf += 10
            if day['rsi'] <= 50: euf -= 10
        if cheap < c['soglia_attivazione']: euf = 0
        if self.banda >= 1: euf = 0
        euf = B.clip(euf)
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
        dca = max(0.0, min(self.budget_dca, self.budget_dca/mondays_left if mondays_left > 0 else self.budget_dca))
        sett_dip = c['budget_mese']*(1-c['quota_dca_frac'])/4
        if b == 3: ideal = min(c['dip_b3_max'], sett_dip + 0.4*self.riserva_dip)
        elif b == 2: ideal = c['dip_b2']
        elif b == 1: ideal = c['dip_b1']
        else:
            ideal = 0.0; mv = min(sett_dip, self.budget_dip); self.budget_dip -= mv; self.riserva_dip += mv
        dip = min(ideal, self.budget_dip + self.riserva_dip)
        take = min(dip, self.budget_dip); self.budget_dip -= take; self.riserva_dip -= (dip - take)
        if b >= 1 and self.riserva_sell > 0:
            if 'prop' in v:
                frac = {1: 0.15, 2: 0.30, 3: 0.50}[b]
                extra = self.riserva_sell*frac
            else:
                extra = max(0.0, min(self.riserva_sell, c['tetto_singolo'] - dca - dip))
            dip += extra; self.riserva_sell -= extra
            if self.riserva_sell < 1e-9: self.riserva_sell = 0.0; self.riserva_sell_scad = None
        self.budget_dca -= dca
        self.carrello += dca + dip
        sell_btc = 0.0
        if self.sell_enabled and bs >= 1:
            total = self.stack + self.sold_cycle
            if 'target' in v:
                target = {1: 0.15, 2: 0.30, 3: 0.50}[bs]*total
                sell_btc = max(0.0, target - self.sold_cycle - self.carrello_sell)
            else:
                residual = max(0.0, c['sell_max_cumulo']*total - self.sold_cycle)
                sell_btc = residual*{1: c['sell_b1'], 2: c['sell_b2'], 3: c['sell_b3']}[bs]
            self.carrello_sell += sell_btc
        elif bs == 0:
            self.carrello_sell = 0.0
        self.execute_buy(d, price)
        if self.sell_enabled and self.carrello_sell*price >= c['carrello_sell_min']:
            self.execute_sell(d, price, self.carrello_sell); self.carrello_sell = 0.0
        if 'noexp' not in v:
            if self.riserva_sell > 0 and self.riserva_sell_scad is not None and d > self.riserva_sell_scad:
                self.budget_dca += self.riserva_sell; self.riserva_sell = 0.0; self.riserva_sell_scad = None
        if self.riserva_sell <= 0 and bs == 0: self.sold_cycle = 0.0
        self.stress_prev = stress; self.euf_prev = euf
        self.log.append(dict(date=d, price=price, cheap=cheap, dd=dd, trend=trend, stress=stress, euf=euf,
                             banda=b, banda_sell=bs, dca=dca, dip=dip, sell_btc=sell_btc, stack=self.stack,
                             riserva_sell=self.riserva_sell, riserva_dip=self.riserva_dip, fng=day['fng'], rsi=day['rsi']))

    # for variants without 'target'/'gate' but with 'prop'/'noexp' we still need the custom path
    def weekly(self, d, day, mondays_left):
        return self.weekly_custom(d, day, mondays_left)

def runv(cfg, dates, daily, start, end, variant):
    eng = EngineV(cfg, variant, sell_enabled=True)
    cur_month = None
    for d in dates:
        if d < start or d > end: continue
        day = daily[d]
        if day['ma200'] is None or day['max365'] is None or day['rsi'] is None: continue
        if (d.year, d.month) != cur_month:
            cur_month = (d.year, d.month); eng.new_month(d)
        if d.weekday() == 0:
            ml = [m for m in B.mondays_in_month(d.year, d.month) if m >= d]
            eng.weekly(d, day, len(ml))
        nxt = d + dt.timedelta(days=1)
        if nxt.month != d.month or d == end: eng.end_month(d, day['close'])
    return eng

if __name__ == '__main__':
    px = B.load_prices(); fng = B.load_fng(); dates, daily = B.build_daily(px, fng)
    end = dt.date(2026, 9, 14)
    starts = [dt.date(2018,2,5), dt.date(2019,1,7), dt.date(2020,1,6), dt.date(2021,1,4), dt.date(2022,1,3), dt.date(2023,1,2), dt.date(2024,1,1)]
    variants = ['spec', 'prop', 'prop+noexp', 'prop+noexp+target', 'prop+noexp+target+gate', 'prop+noexp+gate']
    print(f"{'start':10} {'DCA btc':>9} {'v4':>8} | " + ' '.join(f"{v:>24}" for v in variants))
    for st in starts:
        dca = B.run_dca(B.CFG, dates, daily, st, end)['stack']
        v4 = B.run(B.CFG, dates, daily, st, end, sell_enabled=False)
        p = daily[end]['close']
        va, ca = v4.value(p); v4b = va/p
        cells = []
        for v in variants:
            e = runv(B.CFG, dates, daily, st, end, v)
            val, cash = e.value(p); btc = val/p
            cells.append(f"{btc:.5f} ({btc/dca-1:+.1%},{e.n_sell:2d}s)")
        print(f"{st} {dca:9.5f} {v4b/dca-1:+7.1%} | " + ' '.join(f"{c:>24}" for c in cells))
