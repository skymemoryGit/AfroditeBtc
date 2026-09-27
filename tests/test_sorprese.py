"""Messaggi a sorpresa (D46) — orologio e sorteggio finti, niente rete.

    python3 -m unittest tests.test_sorprese -v
"""

import datetime
import json
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import comandi, config, sorprese, telegram_client
from botbtc import store

D = datetime.datetime
LUNEDI = D(2026, 9, 28, 8, 0)          # lunedì 28 settembre 2026


class Piano(unittest.TestCase):
    def test_tre_in_giorni_feriali_diversi_fra_le_10_e_le_18(self):
        for seme in range(50):
            orari = sorprese.estrai_piano(LUNEDI, 3, 10, 18, True, random.Random(seme))
            self.assertEqual(len(orari), 3)
            self.assertEqual(len({o.date() for o in orari}), 3, "giorni diversi")
            for o in orari:
                self.assertLess(o.weekday(), 5, "solo lunedì-venerdì")
                self.assertTrue(10 <= o.hour < 18, o)
            self.assertEqual(orari, sorted(orari))

    def test_settimana_iniziata_a_metà(self):
        giovedi_sera = D(2026, 10, 1, 17, 58)      # oggi non c'è più spazio: resta solo venerdì
        orari = sorprese.estrai_piano(giovedi_sera, 3, 10, 18, True, random.Random(1))
        self.assertEqual([o.date() for o in orari], [datetime.date(2026, 10, 2)])

    def test_mai_nel_passato_di_oggi(self):
        martedi_14 = D(2026, 9, 29, 14, 0)
        for seme in range(50):
            for o in sorprese.estrai_piano(martedi_14, 3, 10, 18, True, random.Random(seme)):
                self.assertGreater(o, martedi_14)

    def test_venerdi_sera_niente(self):
        self.assertEqual(sorprese.estrai_piano(D(2026, 10, 2, 19, 0), 3, 10, 18, True, random.Random(1)), [])

    def test_anche_nel_fine_settimana_se_richiesto(self):
        giorni = {o.weekday() for s in range(80)
                  for o in sorprese.estrai_piano(LUNEDI, 3, 10, 18, False, random.Random(s))}
        self.assertTrue(giorni & {5, 6})

    def test_spenti_e_tanti(self):
        self.assertEqual(sorprese.estrai_piano(LUNEDI, 0, 10, 18, True, random.Random(1)), [])
        self.assertEqual(len(sorprese.estrai_piano(LUNEDI, 8, 10, 18, True, random.Random(1))), 8)


class Aggiornamento(unittest.TestCase):
    def piano(self, momento, piano=None, quanti=3):
        return sorprese.aggiorna_piano(piano or {}, momento, quanti, 10, 18, True, random.Random(7))

    def test_riavvio_non_rimescola(self):
        p1, _, _ = self.piano(LUNEDI)
        p2, _, _ = sorprese.aggiorna_piano(json.loads(json.dumps(p1)), LUNEDI + datetime.timedelta(hours=1),
                                           3, 10, 18, True, random.Random(999))
        self.assertEqual(p1["orari"], p2["orari"])

    def test_all_ora_giusta_se_ne_manda_uno(self):
        p, _, _ = self.piano(LUNEDI)
        primo = D.fromisoformat(p["orari"][0])
        p, manda, salta = sorprese.aggiorna_piano(p, primo + datetime.timedelta(minutes=1), 3, 10, 18, True)
        self.assertEqual(manda, [p["orari"][0]])
        _, manda_di_nuovo, _ = sorprese.aggiorna_piano(p, primo + datetime.timedelta(minutes=2), 3, 10, 18, True)
        self.assertEqual(manda_di_nuovo, [], "mai due volte lo stesso")

    def test_perso_mentre_era_spento_si_salta(self):
        p, _, _ = self.piano(LUNEDI)
        primo = D.fromisoformat(p["orari"][0])
        il_giorno_dopo = primo.replace(hour=9) + datetime.timedelta(days=1)
        _, manda, salta = sorprese.aggiorna_piano(p, il_giorno_dopo, 3, 10, 18, True)
        self.assertEqual(manda, [])
        self.assertIn(p["orari"][0], salta)

    def test_fuori_fascia_si_salta(self):
        p, _, _ = self.piano(LUNEDI)
        primo = D.fromisoformat(p["orari"][0])
        _, manda, salta = sorprese.aggiorna_piano(p, primo.replace(hour=19), 3, 10, 18, True)
        self.assertEqual(manda, [])

    def test_settimana_nuova_piano_nuovo(self):
        p, _, _ = self.piano(LUNEDI)
        p2, _, _ = self.piano(LUNEDI + datetime.timedelta(days=7), p)
        self.assertNotEqual(p["settimana"], p2["settimana"])
        self.assertTrue(all(o.startswith("2026-10-0") for o in p2["orari"]))

    def test_cambiare_il_numero_nel_env_rifà_il_piano(self):
        p, _, _ = self.piano(LUNEDI)
        p2, _, _ = self.piano(LUNEDI, p, quanti=5)
        self.assertEqual(len(p2["orari"]), 5)


class NelBot(unittest.TestCase):
    """controlla_sorprese vero, su un database dai CSV, con Telegram e rete finti."""

    @classmethod
    def setUpClass(cls):
        cls.cartella = tempfile.mkdtemp()
        cls.conn = store.apri(os.path.join(cls.cartella, "p.sqlite3"))
        store.bootstrap_da_csv(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.cartella, ignore_errors=True)

    def setUp(self):
        if not comandi.padrone():
            self.skipTest("serve BOTBTC_TELEGRAM_CHAT_ID in bot/.env")
        self.inviati = []
        self.originali = (telegram_client.invia, store.aggiorna_da_rete, config.PING_PER_SETTIMANA)
        telegram_client.invia = lambda token, chat, testo, **k: self.inviati.append((str(chat), testo)) or True
        store.aggiorna_da_rete = lambda *a, **k: None
        config.PING_PER_SETTIMANA = 3
        store.scrivi_impostazione(self.conn, sorprese.CHIAVE, "")
        store.scrivi_impostazione(self.conn, "pausa", "0")
        store.scrivi_impostazione(self.conn, "modalita", "quotidiano")

    def tearDown(self):
        telegram_client.invia, store.aggiorna_da_rete, config.PING_PER_SETTIMANA = self.originali

    def primo_orario(self):
        comandi.controlla_sorprese(self.conn, momento=LUNEDI, rng=random.Random(3))
        piano = json.loads(store.leggi_impostazione(self.conn, sorprese.CHIAVE, ""))
        return D.fromisoformat(piano["orari"][0]) + datetime.timedelta(minutes=1)

    def test_manda_il_polso_al_proprietario(self):
        momento = self.primo_orario()
        self.assertEqual(self.inviati, [], "lunedì alle 8 non si manda niente")
        testo = comandi.controlla_sorprese(self.conn, momento=momento)
        self.assertIsNotNone(testo)
        chat, inviato = self.inviati[-1]
        self.assertEqual(chat, comandi.padrone())
        self.assertIn("🔔", inviato)
        self.assertLessEqual(len(inviato.splitlines()), 8, "corto: una riga + il polso (D48)")

    def test_rispetta_pausa_e_silenzioso(self):
        for chiave, valore in (("pausa", "1"), ("modalita", "silenzioso")):
            store.scrivi_impostazione(self.conn, sorprese.CHIAVE, "")
            store.scrivi_impostazione(self.conn, "pausa", "0")
            store.scrivi_impostazione(self.conn, "modalita", "quotidiano")
            momento = self.primo_orario()
            store.scrivi_impostazione(self.conn, chiave, valore)
            self.assertIsNone(comandi.controlla_sorprese(self.conn, momento=momento), chiave)
        self.assertEqual(self.inviati, [])

    def test_spenti_dal_env(self):
        config.PING_PER_SETTIMANA = 0
        self.assertIsNone(comandi.controlla_sorprese(self.conn, momento=LUNEDI.replace(hour=12)))


if __name__ == "__main__":
    unittest.main()
