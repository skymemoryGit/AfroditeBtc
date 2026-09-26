"""Verifiche della fase F2 — il motore dei tre stati.

    python3 -m unittest tests.test_f2 -v

Corrispondenza con le verifiche del piano:
  F2.1  funzione pura: stesso input, stesso output, nessun accesso a rete o file
  F2.2  regole a percentile: nessuna soglia assoluta, monotonia rispetto alla profondita'
  F2.6  degrado con grazia: senza MVRV e Fear & Greed il nucleo di prezzo decide lo stesso
  F2.4  moltiplicatore: limitato, monotono, mai zero quando lo stato e' straordinario
  F2.5  tetto e bande: le fasi poco profonde non possono consumare tutto il tetto
  F2.3  regressione sul caso che ha fatto nascere il progetto: giugno 2026 deve accendersi
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from botbtc import dataset, engine

SOGLIE = {"soglia_straordinario": 0.4229, "soglia_freno": 0.2314, "durata_minima_caro": 60}


def par(**cambi):
    return engine.Parametri(**{**SOGLIE, **cambi})


def tutti(valore):
    return {k: valore for k in engine.PESI}


class F21FunzionePura(unittest.TestCase):
    def test_stesso_input_stesso_output(self):
        pct = {"price_vs_wma200": 8, "mayer": 12, "dd365": 5, "rsi14_w": 20,
               "rsi14_d": 40, "mvrv": 9, "fng": 15}
        a = engine.valuta(dict(pct), par())
        b = engine.valuta(dict(pct), par())
        self.assertEqual(a["stato"], b["stato"])
        self.assertAlmostEqual(a["punteggio_economico"], b["punteggio_economico"])

    def test_non_modifica_gli_ingressi(self):
        pct = tutti(10)
        copia = dict(pct)
        engine.valuta(pct, par())
        self.assertEqual(pct, copia)

    def test_non_dipende_dalla_data_di_oggi(self):
        """Il motore non deve guardare l'orologio: nessuna chiamata a datetime.now al suo interno."""
        sorgente = open(os.path.join(os.path.dirname(__file__), os.pardir, "botbtc", "engine.py"),
                        encoding="utf-8").read()
        for vietato in ("datetime.now", "utcnow", "time.time", "open(", "urllib", "sqlite3"):
            self.assertNotIn(vietato, sorgente, f"engine.py non deve contenere {vietato}")


class F22Percentili(unittest.TestCase):
    def test_piu_economico_punteggio_piu_alto(self):
        p = par()
        precedente = -1
        for percentile in (29, 20, 10, 5, 0):
            punteggio = engine.valuta(tutti(percentile), p)["punteggio_economico"]
            self.assertGreater(punteggio, precedente)
            precedente = punteggio

    def test_zona_neutra_non_contribuisce(self):
        p = par()
        r = engine.valuta(tutti(50), p)
        self.assertEqual(r["punteggio_economico"], 0.0)
        self.assertEqual(r["punteggio_caro"], 0.0)
        self.assertEqual(r["stato"], engine.NORMALE)

    def test_estremi(self):
        p = par()
        self.assertAlmostEqual(engine.valuta(tutti(0), p)["punteggio_economico"], 1.0)
        self.assertAlmostEqual(engine.valuta(tutti(100), p)["punteggio_caro"], 1.0)

    def test_stato_straordinario_e_freno(self):
        p = par()
        self.assertEqual(engine.valuta(tutti(5), p)["stato"], engine.STRAORDINARIO)
        self.assertEqual(engine.valuta(tutti(95), p)["stato"], engine.FRENO)


class F26DegradoConGrazia(unittest.TestCase):
    def test_senza_mvrv_e_fng_il_nucleo_decide(self):
        pct = {"price_vs_wma200": 3, "mayer": 5, "dd365": 4, "rsi14_w": 10, "rsi14_d": 15,
               "mvrv": None, "fng": None}
        r = engine.valuta(pct, par())
        self.assertEqual(r["stato"], engine.STRAORDINARIO)
        self.assertEqual(sorted(r["ingredienti_mancanti"]), ["fng", "mvrv"])
        self.assertAlmostEqual(r["peso_disponibile"], 0.80)

    def test_troppi_ingredienti_mancanti_stato_sconosciuto(self):
        pct = {k: None for k in engine.PESI}
        pct["mvrv"] = 5
        r = engine.valuta(pct, par())
        self.assertEqual(r["stato"], engine.SCONOSCIUTO)
        self.assertIsNone(r["punteggio_economico"])
        self.assertTrue(r["motivi"])

    def test_il_punteggio_resta_sulla_stessa_scala(self):
        """Normalizzando sui pesi disponibili, togliere un ingrediente non cambia la scala."""
        completo = engine.valuta(tutti(0), par())["punteggio_economico"]
        ridotto = engine.valuta({**tutti(0), "mvrv": None, "fng": None}, par())["punteggio_economico"]
        self.assertAlmostEqual(completo, 1.0)
        self.assertAlmostEqual(ridotto, 1.0)


class F2Conferma(unittest.TestCase):
    def test_un_giorno_isolato_non_cambia_lo_stato(self):
        serie = [tutti(50)] * 5 + [tutti(2)] + [tutti(50)] * 5
        righe = engine.serie_stati(serie, par())
        self.assertTrue(all(r["stato_confermato"] == engine.NORMALE for r in righe))

    def test_due_giorni_consecutivi_confermano(self):
        serie = [tutti(50)] * 5 + [tutti(2)] * 3 + [tutti(50)] * 5
        righe = engine.serie_stati(serie, par())
        stati = [r["stato_confermato"] for r in righe]
        self.assertIn(engine.STRAORDINARIO, stati)
        self.assertEqual(stati[6], engine.STRAORDINARIO)   # confermato al secondo giorno

    def test_il_freno_richiede_la_durata(self):
        """Caro da pochi giorni = rialzo giovane, non fase matura (lezione di dicembre 2020)."""
        breve = engine.serie_stati([tutti(95)] * 30, par(durata_minima_caro=60))
        self.assertTrue(all(r["stato_confermato"] != engine.FRENO for r in breve))
        lunga = engine.serie_stati([tutti(95)] * 90, par(durata_minima_caro=60))
        self.assertEqual(lunga[-1]["stato_confermato"], engine.FRENO)


class F24Moltiplicatore(unittest.TestCase):
    def test_limitato_e_monotono(self):
        p = par()
        valori = [engine.moltiplicatore(x, p) for x in (0.43, 0.5, 0.6, 0.8, 0.95, 1.0)]
        self.assertTrue(all(p.molt_min <= v <= p.molt_max for v in valori), valori)
        self.assertEqual(valori, sorted(valori))

    def test_mai_zero_se_lo_stato_e_straordinario(self):
        r = engine.valuta(tutti(28), par())
        if r["stato"] == engine.STRAORDINARIO:
            self.assertGreaterEqual(r["moltiplicatore"], 1.5)

    def test_niente_moltiplicatore_fuori_dallo_stato(self):
        self.assertIsNone(engine.valuta(tutti(50), par())["moltiplicatore"])
        self.assertIsNone(engine.valuta(tutti(95), par())["moltiplicatore"])


class F25TettoETranche(unittest.TestCase):
    def test_le_fasi_poco_profonde_non_consumano_tutto(self):
        p = par()
        # punteggio appena sopra la soglia: al massimo il 30 % del tetto
        self.assertAlmostEqual(engine.tranche_consentita(0.44, 0.0, 12.0, p), 3.6)
        # gia' speso il 30 %: niente piu' capienza a quella profondita'
        self.assertAlmostEqual(engine.tranche_consentita(0.44, 3.6, 12.0, p), 0.0)
        # ma piu' in profondita' si riapre: banda intermedia (fino a 0,60) = 65 % del tetto
        self.assertAlmostEqual(engine.tranche_consentita(0.55, 3.6, 12.0, p), 4.2)
        # e oltre 0,60 si sblocca tutto il tetto residuo
        self.assertAlmostEqual(engine.tranche_consentita(0.70, 3.6, 12.0, p), 8.4)
        self.assertAlmostEqual(engine.tranche_consentita(0.95, 3.6, 12.0, p), 8.4)

    def test_senza_tetto_deciso_non_si_inventa_un_numero(self):
        self.assertIsNone(engine.tranche_consentita(0.8, 0.0, None, par()))


class F23Regressione(unittest.TestCase):
    """Il caso che ha fatto nascere il progetto non deve spegnersi con una modifica futura."""

    @classmethod
    def setUpClass(cls):
        cls.ds = dataset.carica_da_csv(serie="coinmetrics")
        dataset.aggiungi_percentili(cls.ds, 1460)
        percentili = [dataset.percentili_del_giorno(cls.ds, i) for i in range(len(cls.ds))]
        cls.righe = engine.serie_stati(percentili, par())
        cls.stati = {cls.ds.dates[i]: cls.righe[i].get("stato_confermato")
                     for i in range(len(cls.ds))}

    def _giorni(self, da, a, stato):
        return [g for g, s in self.stati.items() if da <= g <= a and s == stato]

    def test_giugno_2026_si_accende(self):
        giorni = self._giorni(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30),
                              engine.STRAORDINARIO)
        self.assertTrue(giorni, "giugno 2026 deve risultare straordinario (criterio (a) di F2.3)")

    def test_gli_altri_tre_casi_storici_si_accendono(self):
        for da, a in ((datetime.date(2018, 12, 1), datetime.date(2018, 12, 31)),
                      (datetime.date(2020, 3, 1), datetime.date(2020, 3, 31)),
                      (datetime.date(2022, 11, 1), datetime.date(2022, 11, 30))):
            self.assertTrue(self._giorni(da, a, engine.STRAORDINARIO), f"{da} - {a}")

    def test_niente_straordinario_nei_tre_mesi_prima_dei_massimi(self):
        for massimo in (datetime.date(2017, 12, 16), datetime.date(2021, 4, 13),
                        datetime.date(2021, 11, 8), datetime.date(2025, 10, 6)):
            giorni = self._giorni(massimo - datetime.timedelta(days=90), massimo,
                                  engine.STRAORDINARIO)
            self.assertFalse(giorni, f"massimo {massimo}: {len(giorni)} giorni straordinari")

    def test_quote_dichiarate(self):
        validi = [s for s in self.stati.values() if s and s != engine.SCONOSCIUTO]
        quota_str = 100 * sum(1 for s in validi if s == engine.STRAORDINARIO) / len(validi)
        quota_fre = 100 * sum(1 for s in validi if s == engine.FRENO) / len(validi)
        self.assertTrue(10 <= quota_str <= 15, f"straordinario {quota_str:.1f}%")
        self.assertLessEqual(quota_fre, 10, f"freno {quota_fre:.1f}%")


if __name__ == "__main__":
    unittest.main(verbosity=2)
