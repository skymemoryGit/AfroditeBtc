"""Verifiche della fase F3 — il testo dei messaggi.

    python3 -m unittest tests.test_f3 -v

Le verifiche del piano che un test PUO' fare (le altre — "si capiscono?" — le fa un essere umano
rileggendo `backtest/messaggi_storici_output.txt`):
  F3.1  il polso resta corto (D48: poche righe, una idea per riga) · l'analisi completa entra in un solo messaggio Telegram
  F3.2  il confronto storico cita l'episodio piu' recente, non la mediana di tutta la storia (D30)
  F3.3  ogni messaggio dichiara la data dei dati · lo straordinario dice sempre che puo' peggiorare ·
        nessun messaggio suona come un ordine (D16)
"""

import datetime
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import config
from botbtc import dataset, engine, messaggi

PARAMETRI = config.parametri_motore()

# Verbi all'imperativo: il bot descrive e suggerisce uno sforzo, non da' ordini.
# "vendere" all'infinito e' ammesso, perche' serve a dire "non e' un invito a vendere".
ORDINI = re.compile(r"\b(compra|comprate|vendi|vendete|acquista|acquistate|liquida)\b", re.I)


class MessaggiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = dataset.carica_da_csv(serie="coinmetrics")
        dataset.aggiungi_percentili(cls.ds, 1460)
        percentili = [dataset.percentili_del_giorno(cls.ds, i) for i in range(len(cls.ds))]
        valori = [{k: cls.ds.ind.get(k, [None] * len(cls.ds))[i] for k in engine.PESI}
                  for i in range(len(cls.ds))]
        cls.righe = engine.serie_stati(percentili, PARAMETRI, valori)

    def tutti_i_formati(self, giorno):
        i = self.ds.indice(giorno)
        foto = dataset.fotografia(self.ds, giorno)
        return {
            "polso": messaggi.polso(self.ds, self.righe, i, foto, PARAMETRI),
            "cambio": messaggi.cambio_stato(self.ds, self.righe, i, foto, PARAMETRI, engine.NORMALE),
            "analisi": messaggi.analisi_completa(self.ds, self.righe, i, foto, PARAMETRI),
        }

    DATE = (datetime.date(2018, 12, 15), datetime.date(2020, 3, 13), datetime.date(2020, 12, 30),
            datetime.date(2021, 11, 8), datetime.date(2022, 11, 9), datetime.date(2026, 6, 29))


class F31Formati(MessaggiBase):
    def test_il_polso_resta_corto(self):
        """D48: non piu' due righe fitte, ma poche righe corte con una idea ciascuna."""
        for giorno in self.DATE:
            testo = self.tutti_i_formati(giorno)["polso"]
            self.assertLessEqual(len(testo.splitlines()), 7, f"{giorno}: {testo}")
            self.assertLess(len(testo), 520, f"{giorno}: {len(testo)} caratteri")
            for riga in testo.splitlines():
                self.assertLess(len(riga), 170, f"{giorno}: riga troppo lunga: {riga}")

    def test_il_polso_non_usa_il_gergo_vecchio(self):
        """D48: "caro al 29% della strada verso il caldo" non lo capiva nessuno."""
        for giorno in self.DATE:
            testo = self.tutti_i_formati(giorno)["polso"]
            self.assertNotIn("della strada", testo, str(giorno))
            self.assertNotIn("ricorrente e basta", testo, str(giorno))
            self.assertIn("💶", testo, f"{giorno}: deve dire cosa fare coi soldi")
            self.assertNotIn("200 €", testo, f"{giorno}: l'importo mensile non si scrive (D50)")

    def test_l_analisi_entra_in_un_messaggio_telegram(self):
        for giorno in self.DATE:
            testo = self.tutti_i_formati(giorno)["analisi"]
            self.assertLess(len(testo), 4096, f"{giorno}: {len(testo)} caratteri")
            self.assertGreater(len(testo), 400, "un'analisi troppo corta non e' un'analisi")

    def test_il_polso_dice_dove_siamo_rispetto_alla_200_wma(self):
        """E' la riga che sarebbe servita a giugno 2026: l'avvicinamento, non solo l'arrivo."""
        for giorno in self.DATE:
            testo = self.tutti_i_formati(giorno)["polso"]
            self.assertIn("200 settimane", testo, str(giorno))

    def test_la_direzione_compare_quando_il_movimento_dura(self):
        testo = self.tutti_i_formati(datetime.date(2022, 11, 9))["polso"]
        self.assertRegex(testo, r"da \d+ giorni (ci si sta avvicinando|se ne sta allontanando|"
                                r"scende ancora|sta risalendo)")


class F32ConfrontoStorico(MessaggiBase):
    def test_cita_l_episodio_piu_recente_non_la_mediana(self):
        giorno = datetime.date(2026, 6, 29)
        i = self.ds.indice(giorno)
        confronto = messaggi.confronto_storico(self.ds, self.righe, i, engine.STRAORDINARIO)
        self.assertIsNotNone(confronto)
        tutti = [e for e in messaggi.episodi(self.ds, self.righe, engine.STRAORDINARIO)
                 if e[1] < giorno - datetime.timedelta(days=30)]
        self.assertEqual(confronto["inizio"], tutti[-1][0],
                         "deve citare l'ultimo episodio passato, non uno qualunque")

    def test_dichiara_che_un_precedente_non_e_una_previsione(self):
        for giorno in (datetime.date(2022, 11, 9), datetime.date(2026, 6, 29)):
            testo = self.tutti_i_formati(giorno)["cambio"]
            self.assertIn("non è una previsione", testo, str(giorno))

    def test_nello_straordinario_dice_che_i_cicli_si_accorciano(self):
        testo = self.tutti_i_formati(datetime.date(2026, 6, 29))["cambio"]
        self.assertIn("ampiezza dei cicli si sta riducendo", testo)


class F33Onesta(MessaggiBase):
    def test_ogni_messaggio_dichiara_la_data_dei_dati(self):
        for giorno in self.DATE:
            for nome, testo in self.tutti_i_formati(giorno).items():
                self.assertTrue("dati del" in testo.lower() or "Dati usati" in testo,
                                f"{giorno} / {nome}: manca la provenienza dei dati")
                self.assertIn("MVRV", testo, f"{giorno} / {nome}")

    def test_lo_straordinario_dice_sempre_che_puo_peggiorare(self):
        for giorno in (datetime.date(2018, 12, 15), datetime.date(2020, 3, 13),
                       datetime.date(2022, 11, 9), datetime.date(2026, 6, 29)):
            for nome in ("cambio", "analisi"):
                testo = self.tutti_i_formati(giorno)[nome]
                if "Straordinario</b>" in testo:
                    self.assertIn("può durare e peggiorare", testo, f"{giorno} / {nome}")
                    self.assertIn("177 giorni", testo, f"{giorno} / {nome}")

    def test_nessun_messaggio_suona_come_un_ordine(self):
        for giorno in self.DATE:
            for nome, testo in self.tutti_i_formati(giorno).items():
                trovato = ORDINI.search(testo)
                self.assertIsNone(trovato, f"{giorno} / {nome}: «{trovato.group(0) if trovato else ''}»")

    def test_il_freno_dice_che_non_e_un_invito_a_vendere(self):
        testo = self.tutti_i_formati(datetime.date(2020, 12, 30))["cambio"]
        self.assertIn("Freno", testo)
        self.assertIn("non è un invito a vendere", testo)

    def test_senza_tetto_deciso_lo_dichiara_invece_di_inventarlo(self):
        testo = self.tutti_i_formati(datetime.date(2022, 11, 9))["cambio"]
        self.assertIn("non l'hai ancora deciso", testo)

    def test_col_tetto_deciso_mostra_il_saldo(self):
        giorno = datetime.date(2022, 11, 9)
        i = self.ds.indice(giorno)
        foto = dataset.fotografia(self.ds, giorno)
        testo = messaggi.cambio_stato(self.ds, self.righe, i, foto, PARAMETRI, engine.NORMALE,
                                      tetto_mesi=12.0, speso_mesi=3.4)
        self.assertIn("usati 3,4 di 12 mesi di budget", testo.replace(".", ","))

    def test_quando_manca_un_ingrediente_lo_dice_col_suo_nome(self):
        """Ultimo giorno: il Fear & Greed non c'e' ancora (F2.6, degrado con grazia)."""
        giorno = self.ds.dates[-1]
        testo = self.tutti_i_formati(giorno)["polso"]
        if "manca" in testo:
            self.assertNotIn("fng", testo, "gli ingredienti vanno chiamati col loro nome")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class F42Comandi(unittest.TestCase):
    """I comandi rispondono, cambiano le impostazioni e non fanno cadere il bot."""

    @classmethod
    def setUpClass(cls):
        import tempfile, os as _os
        from botbtc import store
        from bot import comandi
        cls.comandi = comandi
        cls.store = store
        cls.conn = store.apri(_os.path.join(tempfile.mkdtemp(prefix="botbtc_f42_"), "p.sqlite3"))
        store.bootstrap_da_csv(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_comandi_semplici_rispondono(self):
        for comando, atteso in (("/start", "AphroditeBTC"), ("/guida", "come si legge"),
                                ("/registro", "registro"), ("/sconosciuto", "Non conosco")):
            risposta = self.comandi.gestisci(self.conn, comando)
            self.assertIn(atteso.lower(), risposta.lower(), comando)

    def test_pausa_e_modalita_si_ricordano(self):
        self.comandi.gestisci(self.conn, "/pausa")
        self.assertEqual(self.store.leggi_impostazione(self.conn, "pausa"), "1")
        self.comandi.gestisci(self.conn, "/riprendi")
        self.assertEqual(self.store.leggi_impostazione(self.conn, "pausa"), "0")
        self.comandi.gestisci(self.conn, "/silenzioso")
        self.assertEqual(self.store.leggi_impostazione(self.conn, "modalita"), "silenzioso")
        self.comandi.gestisci(self.conn, "/quotidiano")
        self.assertEqual(self.store.leggi_impostazione(self.conn, "modalita"), "quotidiano")

    def test_perche_spiega_gli_ingredienti(self):
        risposta = self.comandi.gestisci(self.conn, "/perche")
        self.assertIn("I due punteggi", risposta)
        self.assertIn("▮", risposta, "serve la barretta che mostra quanto pesa ogni ingrediente")

    def test_analisi_e_stato_sono_i_messaggi_veri(self):
        analisi = self.comandi.gestisci(self.conn, "/analisi")
        self.assertIn("AphroditeBTC", analisi)
        self.assertLess(len(analisi), 4096)
        stato = self.comandi.gestisci(self.conn, "/stato")
        self.assertLessEqual(len(stato.splitlines()), 7)

    def test_il_comando_accetta_la_forma_con_chiocciola(self):
        self.assertIn("come si legge", self.comandi.gestisci(self.conn, "/guida@AphroBtcbot").lower())


class F42Autorizzazioni(unittest.TestCase):
    """Il bot è personale: chiunque può scrivergli, ma risponde solo a chi è in elenco."""

    @classmethod
    def setUpClass(cls):
        import tempfile, os as _os
        from botbtc import store
        from bot import comandi, config
        cls.comandi, cls.store, cls.config = comandi, store, config
        cls.conn = store.apri(_os.path.join(tempfile.mkdtemp(prefix="botbtc_acl_"), "p.sqlite3"))
        store.bootstrap_da_csv(cls.conn)
        cls.padrone = comandi.padrone() or "999"

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_uno_sconosciuto_riceve_solo_il_suo_id(self):
        risposta = self.comandi.gestisci(self.conn, "/analisi", chat_id="123456")
        self.assertIn("This is a private bot", risposta)       # richiesta dell'utente: il minimo, in inglese
        self.assertIn("123456", risposta)
        self.assertNotIn("MVRV", risposta, "a uno sconosciuto non si manda il report")

    def test_il_comando_id_funziona_per_tutti(self):
        risposta = self.comandi.gestisci(self.conn, "/id", chat_id="123456")
        self.assertIn("123456", risposta)
        self.assertIn("Your ID", risposta)

    def test_il_padrone_autorizza_e_revoca(self):
        self.comandi.gestisci(self.conn, "/autorizza 123456", chat_id=self.padrone)
        self.assertIn("123456", self.comandi.autorizzati(self.conn))
        risposta = self.comandi.gestisci(self.conn, "/stato", chat_id="123456")
        self.assertNotIn("private bot", risposta)
        self.comandi.gestisci(self.conn, "/revoca 123456", chat_id=self.padrone)
        self.assertNotIn("123456", self.comandi.autorizzati(self.conn))

    def test_un_autorizzato_non_puo_gestire_gli_accessi(self):
        self.comandi.gestisci(self.conn, "/autorizza 777", chat_id=self.padrone)
        risposta = self.comandi.gestisci(self.conn, "/autorizza 888", chat_id="777")
        self.assertIn("Solo il proprietario", risposta)
        self.assertNotIn("888", self.comandi.autorizzati(self.conn))
        self.comandi.gestisci(self.conn, "/revoca 777", chat_id=self.padrone)

    def test_il_padrone_non_puo_togliersi_da_solo(self):
        risposta = self.comandi.gestisci(self.conn, f"/revoca {self.padrone}", chat_id=self.padrone)
        self.assertIn("sei il proprietario", risposta)
        self.assertIn(self.padrone, self.comandi.autorizzati(self.conn))

    def test_serve_un_numero(self):
        risposta = self.comandi.gestisci(self.conn, "/autorizza pippo", chat_id=self.padrone)
        self.assertIn("identificativo numerico", risposta)


class D40Caldo(MessaggiBase):
    """Ai massimi di ciclo il messaggio non può dire "nessun estremo" (D40)."""

    MASSIMI = (datetime.date(2021, 11, 8), datetime.date(2025, 10, 6))

    def test_ai_massimi_non_dice_nessun_estremo(self):
        for giorno in self.MASSIMI:
            for nome, testo in self.tutti_i_formati(giorno).items():
                if nome == "cambio":
                    continue            # il cambio stato non si manda: lo stato resta "normale"
                self.assertNotIn("nessun estremo", testo, f"{giorno} / {nome}")
                self.assertIn("🟠 <b>Caldo</b>", testo, f"{giorno} / {nome}")

    def test_il_caldo_non_dice_mai_vendere(self):
        for giorno in self.MASSIMI + (datetime.date(2020, 12, 15),):
            for testo in self.tutti_i_formati(giorno).values():
                self.assertIsNone(ORDINI.search(testo))
                self.assertIn("Non è un segnale di vendita".lower()[:10], testo.lower().replace("non vuol dire vendere", "non è un segnale di vendita"))

    def test_il_caldo_non_e_uno_stato_del_motore(self):
        """Nessuna ri-taratura: lo stato del motore ai massimi resta quello del test storico."""
        for giorno in self.MASSIMI:
            i = self.ds.indice(giorno)
            self.assertEqual(self.righe[i]["stato_confermato"], engine.NORMALE)

    def test_nessun_estremo_solo_quando_entrambi_i_punteggi_sono_sotto_soglia(self):
        for i in range(len(self.ds) - 1500, len(self.ds)):
            r = self.righe[i]
            if r.get("stato_confermato") != engine.NORMALE or r["punteggio_caro"] is None:
                continue
            vista = messaggi.vista_stato(r, PARAMETRI)
            if "nessun estremo" in vista["spiegazione"]:
                self.assertLess(r["punteggio_caro"], PARAMETRI.soglia_freno)
                self.assertLess(r["punteggio_economico"], PARAMETRI.soglia_straordinario)

    def test_niente_precedente_per_il_normale(self):
        """Normale vale l'83% dei giorni: 'l'ultima volta normale' non dice niente."""
        for i in range(len(self.ds) - 60, len(self.ds)):
            if messaggi.condizione(self.righe[i], PARAMETRI) == engine.NORMALE:
                testo = messaggi.analisi_completa(self.ds, self.righe, i,
                                                  dataset.fotografia(self.ds, self.ds.dates[i]), PARAMETRI)
                self.assertNotIn("L'ultima volta", testo)
                break


class D40InArrivo(MessaggiBase):
    def test_il_primo_giorno_sopra_soglia_non_dice_nessun_estremo(self):
        trovati = 0
        for i in range(len(self.ds)):
            r = self.righe[i]
            if (r.get("stato_confermato") == engine.NORMALE and r["punteggio_economico"] is not None
                    and r["punteggio_economico"] >= PARAMETRI.soglia_straordinario):
                vista = messaggi.vista_stato(r, PARAMETRI)
                self.assertEqual(vista["chiave"], messaggi.IN_ARRIVO, str(self.ds.dates[i]))
                self.assertNotIn("nessun estremo", vista["spiegazione"])
                trovati += 1
        self.assertGreater(trovati, 0, "il caso deve esistere nella storia, altrimenti il test non prova niente")
