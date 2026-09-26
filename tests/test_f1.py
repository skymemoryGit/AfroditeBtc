"""Verifiche delle fasi F0 e F1 (piano di sviluppo §F0-F1).

Si lanciano senza rete:  python3 -m unittest discover -s tests -v
I test che richiedono la rete stanno in `tests/prova_rete.py` (da lanciare a mano dal PC o dal VPS).

Ogni test corrisponde a una "verifica" scritta nel piano:
  F0.1  la configurazione si stampa senza toccare rete o database
  F1.1  un fetcher senza rete fallisce in modo pulito e leggibile, non restituisce numeri finti
  F1.2  due esecuzioni di fila: la seconda non scarica niente e non duplica righe
  F1.3  una riga sballata iniettata a mano viene intercettata
  F1.4  gli indicatori calcolati dal database coincidono con quelli di validate_mvrv.py
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import config
from botbtc import dataset, fetchers, sanity, store


def _db_temporaneo():
    cartella = tempfile.mkdtemp(prefix="botbtc_test_")
    return os.path.join(cartella, "prova.sqlite3")


class F0Configurazione(unittest.TestCase):
    def test_riassunto_completo_e_senza_effetti(self):
        r = config.riassunto()
        for chiave in ("budget mensile", "finestra percentile", "orario report"):
            self.assertIn(chiave, r)
        self.assertIn("EUR", r["budget mensile"])

    def test_budget_e_un_parametro(self):
        self.assertGreater(config.BUDGET_MENSILE_EUR, 0)
        self.assertEqual(config.FINESTRA_PERCENTILE_GIORNI, 1460)
        self.assertIn(config.FINESTRA_PERCENTILE_GIORNI, config.FINESTRE_PERCENTILE_SENSIBILITA)


class F11Fetcher(unittest.TestCase):
    def test_errore_esplicito_se_la_fonte_non_risponde(self):
        """Host inesistente: deve alzare FetchError con fonte, url e motivo — mai restituire dati."""
        vecchio = fetchers.COINBASE_URL
        fetchers.COINBASE_URL = "https://host-che-non-esiste.invalid/{prodotto}/candles"
        try:
            with self.assertRaises(fetchers.FetchError) as ctx:
                fetchers.prezzo_coinbase(datetime.date(2026, 9, 1), datetime.date(2026, 9, 2),
                                         timeout=3, tentativi=1)
            errore = ctx.exception
            self.assertEqual(errore.fonte, "coinbase")
            self.assertTrue(str(errore))
        finally:
            fetchers.COINBASE_URL = vecchio

    def test_fallback_riporta_gli_errori_della_primaria(self):
        vecchi = (fetchers.COINBASE_URL, fetchers.BINANCE_URL)
        fetchers.COINBASE_URL = "https://host-che-non-esiste.invalid/{prodotto}/candles"
        fetchers.BINANCE_URL = "https://altro-host-inesistente.invalid/klines"
        try:
            with self.assertRaises(fetchers.FetchError) as ctx:
                fetchers.prezzo_con_fallback(datetime.date(2026, 9, 1), datetime.date(2026, 9, 2),
                                             timeout=3, tentativi=1)
            self.assertIn("nessuna fonte disponibile", str(ctx.exception))
        finally:
            fetchers.COINBASE_URL, fetchers.BINANCE_URL = vecchi


class F12Archivio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.percorso = _db_temporaneo()
        cls.conn = store.apri(cls.percorso)
        cls.caricate = store.bootstrap_da_csv(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_bootstrap_carica_i_tre_csv(self):
        for tabella in store.TABELLE:
            self.assertGreater(self.caricate[tabella], 1000, tabella)

    def test_seconda_esecuzione_non_ricarica(self):
        di_nuovo = store.bootstrap_da_csv(self.conn)
        self.assertEqual(set(di_nuovo.values()), {0})

    def test_scrivere_due_volte_lo_stesso_giorno_non_duplica(self):
        prima = store.conteggi(self.conn)["prezzi"]
        giorno = datetime.date(2026, 9, 17)
        store.upsert_prezzi(self.conn, [(giorno, 12345.0)], "prova")
        store.upsert_prezzi(self.conn, [(giorno, 12345.0)], "prova")
        self.assertEqual(store.conteggi(self.conn)["prezzi"], prima)
        riga = self.conn.execute("SELECT chiusura, fonte FROM prezzi WHERE data=?",
                                 (giorno.isoformat(),)).fetchone()
        self.assertAlmostEqual(riga["chiusura"], 12345.0)
        self.assertEqual(riga["fonte"], "prova")
        # ripristino il valore vero per non disturbare gli altri test
        store.upsert_prezzi(self.conn, [(giorno, 76757.02)], "coinbase (csv storico)")

    def test_aggiornamento_senza_rete_non_rompe_e_lo_dichiara(self):
        vecchi = (fetchers.COINBASE_URL, fetchers.BINANCE_URL, fetchers.FNG_URL, fetchers.COINMETRICS_URL)
        fetchers.COINBASE_URL = "https://host-che-non-esiste.invalid/{prodotto}/candles"
        fetchers.BINANCE_URL = "https://host-che-non-esiste.invalid/klines"
        fetchers.FNG_URL = "https://host-che-non-esiste.invalid/fng/"
        fetchers.COINMETRICS_URL = "https://host-che-non-esiste.invalid/v4/timeseries/asset-metrics"
        try:
            prima = store.conteggi(self.conn)
            rapporto = store.aggiorna_da_rete(self.conn, timeout=3, tentativi=1)
            self.assertEqual(store.conteggi(self.conn), prima, "nessuna riga inventata")
            for fonte, voce in rapporto.items():
                self.assertEqual(voce["nuove"], 0, fonte)
                # o ha provato e fallito (errore dichiarato), o non aveva nulla da scaricare
                # (nota): mai un silenzio che sembra un successo
                self.assertTrue(voce["errore"] or voce["nota"],
                                f"{fonte}: deve dire o l'errore o perche' non ha scaricato")
        finally:
            (fetchers.COINBASE_URL, fetchers.BINANCE_URL,
             fetchers.FNG_URL, fetchers.COINMETRICS_URL) = vecchi


class F13Sanita(unittest.TestCase):
    def setUp(self):
        self.dates = [datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(10)]
        self.valori = [100.0 + i for i in range(10)]
        self.oggi = self.dates[-1]

    def test_serie_pulita_non_genera_problemi(self):
        self.assertEqual(sanity.controlla_serie(self.dates, self.valori, "prova", oggi=self.oggi), [])

    def test_buco_intercettato(self):
        dates = self.dates[:5] + self.dates[6:]
        valori = self.valori[:5] + self.valori[6:]
        tipi = [p.tipo for p in sanity.controlla_serie(dates, valori, "prova", oggi=self.oggi)]
        self.assertIn("buchi", tipi)

    def test_salto_di_prezzo_intercettato(self):
        valori = list(self.valori)
        valori[5] = valori[4] * 2          # +100 % in un giorno
        problemi = sanity.controlla_serie(self.dates, valori, "prova", oggi=self.oggi)
        self.assertIn("salto", [p.tipo for p in problemi])

    def test_data_nel_futuro_intercettata(self):
        dates = list(self.dates)
        dates[-1] = self.oggi + datetime.timedelta(days=5)
        problemi = sanity.controlla_serie(dates, self.valori, "prova", oggi=self.oggi)
        self.assertIn("futuro", [p.tipo for p in problemi])

    def test_valore_impossibile_intercettato(self):
        valori = list(self.valori)
        valori[3] = -1.0
        problemi = sanity.controlla_serie(self.dates, valori, "prova", oggi=self.oggi,
                                          minimo_ammesso=1e-9)
        self.assertIn("valore_non_valido", [p.tipo for p in problemi])

    def test_freschezza_distingue_ritardo_normale_ritardo_anomalo_e_dato_vecchio(self):
        """Per l'MVRV il dato di ieri e' la norma (ritardo strutturale T+1), non un problema."""
        oggi = datetime.date(2026, 9, 20)
        normale = sanity.controlla_freschezza("mvrv", datetime.date(2026, 9, 19), oggi, 3, 1)
        self.assertEqual(normale, [], "il dato di ieri e' quello che ci si aspetta")
        in_ritardo = sanity.controlla_freschezza("mvrv", datetime.date(2026, 9, 18), oggi, 3, 1)
        self.assertEqual(in_ritardo[0].gravita, "avviso")
        vecchio = sanity.controlla_freschezza("mvrv", datetime.date(2026, 9, 10), oggi, 3, 1)
        self.assertEqual(vecchio[0].gravita, "grave")
        assente = sanity.controlla_freschezza("mvrv", None, oggi, 3, 1)
        self.assertEqual(assente[0].tipo, "assente")

    def test_fng_il_salto_si_misura_in_punti(self):
        dates = self.dates[:3]
        # da 3 a 8 e' +167 % ma sono 5 punti: non deve essere segnalato
        problemi = sanity.controlla_serie(dates, [3, 8, 10], "fng", oggi=self.oggi,
                                          salto_assoluto_max=40, minimo_ammesso=0)
        self.assertEqual([p.tipo for p in problemi], [])
        # da 10 a 80 sono 70 punti: va segnalato
        problemi = sanity.controlla_serie(dates, [10, 80, 75], "fng", oggi=self.oggi,
                                          salto_assoluto_max=40, minimo_ammesso=0)
        self.assertIn("salto", [p.tipo for p in problemi])


class F14PonteIndicatori(unittest.TestCase):
    """I numeri devono coincidere con docs/02 §7-bis, cioe' con validate_mvrv.py."""

    ATTESI_2026_09_19 = {
        "prezzo": 81262, "mayer": 1.15, "dd365": -34.9, "rsi14_d": 64.3, "rsi14_w": 58.8,
        "price_vs_wma200": 1.24, "pi_ratio": 0.43, "mvrv": 1.526, "mvrv_z": 0.92, "mvrv_pct": 43.0,
    }

    @classmethod
    def setUpClass(cls):
        cls.conn = store.apri(_db_temporaneo())
        store.bootstrap_da_csv(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_serie_coinmetrics_riproduce_i_numeri_del_documento(self):
        ds = dataset.carica(self.conn, serie="coinmetrics")
        foto = dataset.fotografia(ds, datetime.date(2026, 9, 19))
        for chiave, atteso in self.ATTESI_2026_09_19.items():
            ottenuto = foto[chiave]
            self.assertIsNotNone(ottenuto, chiave)
            tolleranza = 1.0 if chiave == "prezzo" else 0.06
            self.assertLess(abs(ottenuto - atteso), tolleranza,
                            f"{chiave}: atteso {atteso}, ottenuto {ottenuto}")

    def test_percentili_su_tutte_le_finestre_per_il_test_di_sensibilita(self):
        ds = dataset.carica(self.conn, serie="coinmetrics")
        i = ds.indice(datetime.date(2026, 9, 19))
        for finestra in dataset.FINESTRE_PERCENTILE:
            valore = ds.ind[f"mvrv_pct{finestra}"][i]
            self.assertIsNotNone(valore, finestra)
            self.assertTrue(0 <= valore <= 100)

    def test_serie_coinbase_e_il_nucleo_di_soli_prezzi(self):
        ds = dataset.carica(self.conn, serie="coinbase")
        foto = dataset.fotografia(ds)
        self.assertTrue(foto["nucleo_completo"])
        self.assertEqual(foto["data"], ds.dates[-1])
        # le due serie di prezzo non coincidono al centesimo, ma raccontano la stessa storia
        ds_cm = dataset.carica(self.conn, serie="coinmetrics")
        foto_cm = dataset.fotografia(ds_cm, foto["data"])
        self.assertLess(abs(foto["prezzo"] / foto_cm["prezzo"] - 1), 0.05)

    def test_mvrv_mancante_non_zittisce_il_bot(self):
        """Se l'MVRV si ferma a tre giorni fa, il nucleo di prezzo resta calcolabile (F2.6)."""
        conn = store.apri(_db_temporaneo())
        store.bootstrap_da_csv(conn)
        limite = datetime.date(2026, 9, 14)
        conn.execute("DELETE FROM mvrv WHERE data > ?", (limite.isoformat(),))
        conn.commit()
        ds = dataset.carica(conn, serie="coinbase")
        foto = dataset.fotografia(ds)
        self.assertTrue(foto["nucleo_completo"])
        self.assertIn("mvrv", foto["ingredienti_mancanti"])
        self.assertEqual(foto["mvrv_data"], limite)
        self.assertGreaterEqual(foto["mvrv_ritardo_giorni"], 3)
        conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)


class F12GiaAggiornato(unittest.TestCase):
    """Se l'archivio ha gia' l'ultimo dato possibile, la rete non si tocca (e non e' un guasto)."""

    def test_nessuna_chiamata_se_c_e_gia_ieri(self):
        conn = store.apri(_db_temporaneo())
        store.bootstrap_da_csv(conn)
        oggi = datetime.date(2026, 9, 20)
        ieri = datetime.date(2026, 9, 19)
        store.upsert_prezzi(conn, [(ieri, 81233.91)], "coinbase")
        store.upsert_fng(conn, [(oggi, 71)])
        vecchi = (fetchers.COINBASE_URL, fetchers.BINANCE_URL, fetchers.FNG_URL, fetchers.COINMETRICS_URL)
        for nome in ("COINBASE_URL", "BINANCE_URL", "FNG_URL", "COINMETRICS_URL"):
            setattr(fetchers, nome, "https://se-chiami-questo-host-il-test-fallisce.invalid/x")
        try:
            rapporto = store.aggiorna_da_rete(conn, oggi=oggi, timeout=2, tentativi=1)
            for fonte, voce in rapporto.items():
                self.assertIsNone(voce["errore"], f"{fonte}: non doveva chiamare la rete")
                self.assertTrue(voce["nota"], f"{fonte}: deve dire perche' non ha scaricato")
        finally:
            (fetchers.COINBASE_URL, fetchers.BINANCE_URL,
             fetchers.FNG_URL, fetchers.COINMETRICS_URL) = vecchi
            conn.close()
