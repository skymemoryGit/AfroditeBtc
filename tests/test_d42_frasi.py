"""Verifiche della D42 — i confronti coi 4 anni detti con i giorni veri, in un verso solo.

    python3 -m unittest tests.test_d42_frasi -v

Richiesta dell'utente (2026-09-23): «"26 giorni su 100" mi fa pensare a 100 giorni veri».
Ora ogni riga dice "negli ultimi 4 anni è stato più alto di oggi in 386 giorni su 1.460 (26%)":
giorni contati davvero sulla finestra dei percentili, sempre nello stesso verso.
Questi test impediscono di tornare alla vecchia forma per sbaglio.
"""

import datetime
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import comandi, config
from botbtc import dataset, engine, messaggi

PARAMETRI = config.parametri_motore()

VECCHIE_FORME = re.compile(r"giorni su 100|più economici di oggi|più cari di oggi|"
                           r"più basso dell?['\s]|più alto dell?['\s]\d")
FORMA = re.compile(r"negli ultimi \d+ anni è stato più alto di oggi in [\d.]+ giorni su [\d.]+ "
                   r"\((\d+%|meno dell'1%)\)(, uguale in altri [\d.]+)?"
                   r"|negli ultimi \d+ anni non è mai stato più alto di oggi \(uguale in [\d.]+ giorni su [\d.]+\)"
                   r"|il valore più (alto|basso) degli ultimi \d+ anni")
DATE = (datetime.date(2018, 12, 15), datetime.date(2020, 3, 13), datetime.date(2020, 12, 30),
        datetime.date(2021, 11, 8), datetime.date(2022, 11, 9), datetime.date(2026, 6, 29))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = dataset.carica_da_csv(serie="coinmetrics")
        dataset.aggiungi_percentili(cls.ds, 1460)
        percentili = [dataset.percentili_del_giorno(cls.ds, i) for i in range(len(cls.ds))]
        valori = [{k: cls.ds.ind.get(k, [None] * len(cls.ds))[i] for k in engine.PESI}
                  for i in range(len(cls.ds))]
        cls.righe = engine.serie_stati(percentili, PARAMETRI, valori)

    def formati(self, giorno):
        i = self.ds.indice(giorno)
        foto = dataset.fotografia(self.ds, giorno)
        return {"polso": messaggi.polso(self.ds, self.righe, i, foto, PARAMETRI),
                "cambio": messaggi.cambio_stato(self.ds, self.righe, i, foto, PARAMETRI, engine.NORMALE),
                "analisi": messaggi.analisi_completa(self.ds, self.righe, i, foto, PARAMETRI),
                "perche": comandi._perche(self.ds, self.righe, i, foto, PARAMETRI)}


class LaFrase(unittest.TestCase):
    def test_forma_approvata_dall_utente(self):
        self.assertEqual(engine.confronto_in_giorni(386, 1460),
                         "negli ultimi 4 anni è stato più alto di oggi in 386 giorni su 1.460 (26%)")

    def test_i_pareggi_si_dicono(self):
        # il drawdown vale 0 in ogni giorno di nuovo massimo annuale: 0 e' il massimo, ma non e' unico
        self.assertEqual(engine.confronto_in_giorni(0, 1460, 4, uguali=121),
                         "negli ultimi 4 anni non è mai stato più alto di oggi (uguale in 121 giorni su 1.460)")
        self.assertTrue(engine.confronto_in_giorni(183, 1374, 4, uguali=25).endswith("(13%), uguale in altri 25"))
        self.assertNotIn("uguale", engine.confronto_in_giorni(183, 1374, 4, uguali=5))   # sotto l'1%: rumore

    def test_estremi_detti_a_parole(self):
        self.assertEqual(engine.confronto_in_giorni(0, 1460), "il valore più alto degli ultimi 4 anni")
        self.assertEqual(engine.confronto_in_giorni(1459, 1460), "il valore più basso degli ultimi 4 anni")
        self.assertIn("(meno dell'1%)", engine.confronto_in_giorni(3, 1460))

    def test_migliaia_all_italiana(self):
        self.assertIn("in 1.236 giorni su 1.460 (85%)", engine.confronto_in_giorni(1236, 1460))

    def test_grammatica_di_chi_spinge(self):
        contributi = {k: {"caro": 0.5, "economico": 0.0, "peso": 1.0} for k in list(engine.PESI)[:4]}
        self.assertTrue(messaggi.chi_contribuisce({"contributi": contributi}, "caro").endswith("e un altro"))
        contributi = {k: {"caro": 0.5, "economico": 0.0, "peso": 1.0} for k in list(engine.PESI)[:5]}
        self.assertTrue(messaggi.chi_contribuisce({"contributi": contributi}, "caro").endswith("e altri 2"))


class NeiMessaggi(Base):
    def test_nessuna_vecchia_forma_in_nessun_formato(self):
        for giorno in DATE:
            for nome, testo in self.formati(giorno).items():
                trovato = VECCHIE_FORME.search(testo)
                self.assertIsNone(trovato, f"{giorno} {nome}: {trovato and trovato.group(0)!r}")
        self.assertIsNone(VECCHIE_FORME.search(messaggi.guida()))

    def test_ogni_confronto_ha_la_forma_nuova(self):
        for giorno in DATE:
            for nome in ("analisi", "cambio", "perche"):
                testo = self.formati(giorno)[nome]
                pezzi = re.findall(r"(negli ultimi \d+ anni[^;·<\n]*|il valore più \w+ degli ultimi \d+ anni)", testo)
                self.assertTrue(pezzi or nome == "cambio", f"{giorno} {nome}: nessun confronto")
                for pezzo in pezzi:
                    self.assertRegex(pezzo, FORMA, f"{giorno} {nome}")

    def test_il_perche_dice_i_giorni_di_ogni_indicatore(self):
        testo = self.formati(datetime.date(2026, 6, 29))["perche"]
        self.assertGreaterEqual(len(FORMA.findall(testo)), 5, testo)


class IlConto(Base):
    def test_coerente_col_percentile_del_motore(self):
        for giorno in DATE:
            i = self.ds.indice(giorno)
            for chiave in engine.PESI:
                pct = (self.ds.ind.get(f"pct_{chiave}") or [None] * len(self.ds))[i]
                conto = messaggi.quanti_piu_alti(self.ds, chiave, i)
                self.assertEqual(pct is None, conto is None, f"{giorno} {chiave}")
                if conto:
                    # conto esatto, non approssimato: più alti + uguali + più bassi = tutti gli altri giorni
                    piu_bassi = round(pct * (conto["totale"] - 1) / 100.0)
                    self.assertEqual(conto["piu_alti"] + conto["uguali"] + piu_bassi, conto["totale"] - 1,
                                     f"{giorno} {chiave}")

    def test_la_zona_scritta_coincide_col_punteggio(self):
        for giorno in DATE:
            i = self.ds.indice(giorno)
            contributi = self.righe[i]["contributi"]
            for chiave, c in contributi.items():
                conto = messaggi.quanti_piu_alti(self.ds, chiave, i)
                if not conto or abs(c["percentile"] - 70) < 1 or abs(c["percentile"] - 30) < 1:
                    continue
                self.assertEqual(c["caro"] > 0, conto["quota"] < 30, f"{giorno} {chiave}")
                self.assertEqual(c["economico"] > 0, conto["quota"] > 70, f"{giorno} {chiave}")

    def test_niente_lookahead(self):
        i = self.ds.indice(datetime.date(2021, 11, 8))
        for chiave in ("mayer", "mvrv", "price_vs_wma200"):
            prima = messaggi.quanti_piu_alti(self.ds, chiave, i)
            originale = self.ds.ind[chiave]
            try:
                self.ds.ind[chiave] = originale[:i + 1] + [x * 10 if x else x for x in originale[i + 1:]]
                self.assertEqual(messaggi.quanti_piu_alti(self.ds, chiave, i), prima, chiave)
            finally:
                self.ds.ind[chiave] = originale

    def test_i_motivi_senza_conteggi_hanno_lo_stesso_verso(self):
        i = self.ds.indice(datetime.date(2026, 6, 29))
        r = self.righe[i]
        valori = {k: self.ds.ind.get(k, [None] * len(self.ds))[i] for k in engine.PESI}
        for stato in (engine.STRAORDINARIO, engine.NORMALE):
            for riga in engine.motivi(r["contributi"], stato, valori):
                self.assertNotIn("più basso", riga.replace("il valore più basso", ""), riga)


if __name__ == "__main__":
    unittest.main()
