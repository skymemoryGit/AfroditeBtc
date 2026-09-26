"""Il bot non deve mai usare il futuro (D41).

    python3 -m unittest tests.test_lookahead -v

La prova e' semplice e severa: si taglia lo storico a un giorno X, come se X fosse "oggi", e si
ricalcola tutto. Stato, punteggi e ogni singolo indicatore del giorno X devono essere IDENTICI a
quelli calcolati con lo storico completo. Se non lo sono, il calcolo "sul passato" sta usando
qualcosa che il giorno X non poteva sapere — e il test storico non direbbe la verita' sul bot live.

Questo test ha trovato una perdita vera il 2026-09-22: gli indicatori settimanali decidevano quali
settimane fossero chiuse guardando la domenica della settimana in corso, cioe' il futuro.
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import config
from botbtc import dataset, engine

PARAMETRI = config.parametri_motore()

# Giorni scelti apposta: meta' settimana, fine settimana, primo giorno di uno straordinario,
# un massimo, un minimo, il giorno prima di giugno 2026.
GIORNI = [datetime.date(2018, 12, 15), datetime.date(2020, 3, 13), datetime.date(2020, 12, 30),
          datetime.date(2021, 11, 8), datetime.date(2022, 11, 9), datetime.date(2025, 10, 6),
          datetime.date(2026, 6, 5), datetime.date(2026, 6, 6)]
INDICATORI = ("sma200", "mayer", "dd365", "rsi14_d", "rsi14_w", "wma200", "price_vs_wma200",
              "pi_ratio", "mvrv", "fng", "trends")


def _calcola(a=None):
    ds = dataset.carica_da_csv(serie="coinmetrics", a=a)
    dataset.aggiungi_percentili(ds, 1460)
    percentili = [dataset.percentili_del_giorno(ds, i) for i in range(len(ds))]
    return ds, engine.serie_stati(percentili, PARAMETRI)


class NessunLookahead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds, cls.righe = _calcola()

    def test_ogni_indicatore_e_identico_se_taglio_lo_storico(self):
        for giorno in GIORNI:
            ds_x, _ = _calcola(a=giorno)
            i, j = self.ds.indice(giorno), ds_x.indice(giorno)
            for chiave in INDICATORI:
                a, b = self.ds.ind[chiave][i], ds_x.ind[chiave][j]
                if a is None and b is None:
                    continue
                self.assertIsNotNone(a, f"{giorno} {chiave}")
                self.assertIsNotNone(b, f"{giorno} {chiave}")
                self.assertAlmostEqual(a, b, places=9, msg=f"{giorno}: {chiave} usa il futuro")

    def test_stato_e_punteggi_identici_se_taglio_lo_storico(self):
        for giorno in GIORNI:
            _, righe_x = _calcola(a=giorno)
            a, b = self.righe[self.ds.indice(giorno)], righe_x[-1]
            self.assertEqual(a["stato_confermato"], b["stato_confermato"], str(giorno))
            self.assertAlmostEqual(a["punteggio_economico"], b["punteggio_economico"], places=12,
                                   msg=f"{giorno}: punteggio economico")
            self.assertAlmostEqual(a["punteggio_caro"], b["punteggio_caro"], places=12,
                                   msg=f"{giorno}: punteggio caro")


if __name__ == "__main__":
    unittest.main(verbosity=2)
