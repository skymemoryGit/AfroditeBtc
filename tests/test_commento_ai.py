"""Verifiche di /ai_commentary (D44) — tutte offline, con un modello finto: niente rete, niente costi.

    python3 -m unittest tests.test_commento_ai -v

Cosa si pretende: che un numero inventato non arrivi mai all'utente, che un invito a comprare o vendere non
arrivi mai all'utente, che la chiave non compaia mai in un messaggio d'errore, che il comando funzioni con
qualunque maiuscola (/Ai_commentary), e che senza configurazione il bot dica cosa manca invece di rompersi.
"""

import datetime
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import commento_ai as ca

RIEMPITIVO = (" Il bot guarda il mercato ogni giorno, confronta ogni indicatore con la sua storia recente e descrive"
              " la fase senza dare ordini: il versamento resta una scelta di chi legge.") * 4


def lungo(frase):
    """Un commento finto completo: la frase da provare più un testo neutro senza numeri."""
    return frase + RIEMPITIVO


FONTE = ("PREZZO 84.093 $ · -0,3% 24h · +4,0% 7g · dal massimo degli ultimi 12 mesi -32,6% · 124.720 $ il 06/10/2025 · "
         "Mayer 1,19 · più alto di oggi in 485 giorni su 1.460 (33%) · MVRV 1,57 · Fear & Greed 71/100 · "
         "ai massimi passati 4,43 · 3,43 · 2,85 · 2,29 (2017 → 2025) · dati del 25/09/2026 · 200 euro al mese")


class Numeri(unittest.TestCase):
    def ok(self, frase):
        self.assertEqual(ca.numeri_inventati(frase, FONTE), [], frase)

    def ko(self, frase, atteso):
        self.assertIn(atteso, ca.numeri_inventati(frase, FONTE), frase)

    def test_numeri_copiati(self):
        for frase in ("Bitcoin vale 84.093 dollari", "il Mayer è a 1,19", "in 485 giorni su 1.460 (33%)",
                      "-32,6% dal massimo", "il 25/09/2026", "tra il 2017 e il 2025", "200 euro al mese"):
            self.ok(frase)

    def test_arrotondamenti_ammessi(self):
        for frase in ("circa 84 mila dollari", "circa 84.000 dollari", "un MVRV di circa 1,6",
                      "il Mayer intorno a 1,2", "quasi 125 mila dollari", "un calo del 33% circa"):
            self.ok(frase)

    def test_interi_piccoli_per_contare(self):
        self.ok("tre indicatori su 7, negli ultimi 4 anni")

    def test_numeri_inventati(self):
        self.ko("potrebbe tornare a 90.000 dollari", "90.000")
        self.ko("come nel crollo del 2022", "2022")
        self.ko("un MVRV di 2,5", "2,5")
        self.ko("più alto nel 45% dei giorni", "45")
        self.ko("verso i 150 mila dollari", "150 mila")


class Parole(unittest.TestCase):
    def test_inviti_consigli_previsioni(self):
        for frase, atteso in (("Compra ora finché è basso", "verbi"), ("dovresti vendere una parte", "consigli"),
                              ("è il momento di entrare", "consigli"), ("il prezzo salirà presto", "previsioni"),
                              ("conviene acquistare", "verbi")):
            problemi = ca.parole_vietate(frase)
            self.assertTrue(any(p.startswith(atteso) for p in problemi), (frase, problemi))

    def test_frasi_lecite(self):
        for frase in ("il freno non vuol dire vendere", "quando in tanti vendono per paura",
                      "gli acquisti ricorrenti", "varrebbe versare un po' di più", "se il prezzo scendesse"):
            self.assertEqual(ca.parole_vietate(frase), [], frase)


class Flusso(unittest.TestCase):
    ARGS = ("<b>REPORT</b> " + FONTE, "guida", 200.0, "https://esempio/v1/chat/completions", "modello", "chiave")

    def test_non_configurato_dice_cosa_manca(self):
        ok, testo = ca.commenta("r", "g", 200.0, None, None, None)
        self.assertFalse(ok)
        self.assertIn("BOTBTC_LLM_URL", testo)
        self.assertIn("BOTBTC_LLM_MODELLO", testo)

    def test_commento_buono_passa_con_intestazione_e_chiusura(self):
        ok, testo = ca.commenta(*self.ARGS, data=datetime.date(2026, 9, 25),
                                chiama=lambda m: lungo("Bitcoin è in una fase normale, a circa 84 mila dollari."))
        self.assertTrue(ok, testo)
        self.assertIn("il commento di oggi", testo)
        self.assertIn("25/09/2026", testo)
        self.assertIn(ca.CHIUSURA, testo)

    def test_secondo_tentativo_con_i_problemi(self):
        risposte = iter([lungo("Il prezzo salirà a 90.000 dollari."), lungo("Fase normale, circa 84 mila dollari.")])
        ricevuti = []

        def finto(messaggi):
            ricevuti.append(messaggi)
            return next(risposte)
        ok, testo = ca.commenta(*self.ARGS, chiama=finto)
        self.assertTrue(ok, testo)
        self.assertEqual(len(ricevuti), 2)
        correzione = ricevuti[1][-1]["content"]
        self.assertIn("90.000", correzione)
        self.assertIn("salirà", correzione)

    def test_due_volte_sbagliato_non_si_manda(self):
        ok, testo = ca.commenta(*self.ARGS, chiama=lambda m: "Compra: arriverà a 150 mila dollari.")
        self.assertFalse(ok)
        self.assertIn("non ha passato i miei controlli", testo)
        self.assertNotIn("Compra:", testo.split("\n", 1)[0])

    def test_errore_del_modello(self):
        def guasto(m):
            raise ca.ErroreModello("HTTP 401: non autorizzato")
        ok, testo = ca.commenta(*self.ARGS, chiama=guasto)
        self.assertFalse(ok)
        self.assertIn("/analisi", testo)

    def test_sovraccarico_frase_corta_e_una_seconda_prova(self):
        """Il 503 "high demand" di Gemini arrivava su Telegram col JSON intero: ora una frase corta."""
        ca.ATTESA_SE_OCCUPATO = 0
        chiamate = []

        def occupato(m):
            chiamate.append(1)
            raise ca.ErroreModello('HTTP 503: [{"error": {"code": 503, "status": "UNAVAILABLE"}}]', codice=503)
        ok, testo = ca.commenta(*self.ARGS, chiama=occupato)
        self.assertFalse(ok)
        self.assertEqual(len(chiamate), 2, "una seconda prova da solo, non di più")
        self.assertIn("molto richiesta", testo)
        self.assertNotIn("UNAVAILABLE", testo)
        self.assertNotIn("503", testo)
        self.assertLessEqual(len(testo.splitlines()), 2)

    def test_sovraccarico_passeggero_si_supera(self):
        ca.ATTESA_SE_OCCUPATO = 0
        risposte = [ca.ErroreModello("HTTP 503", codice=503)]

        def una_volta(m):
            if risposte:
                raise risposte.pop()
            return "Fase normale e tranquilla." + RIEMPITIVO
        ok, testo = ca.commenta(*self.ARGS, chiama=una_volta)
        self.assertTrue(ok, testo)

    def test_errori_tecnici_non_arrivano_all_utente(self):
        for errore in (ca.ErroreModello("HTTP 401: invalid key", codice=401),
                       ca.ErroreModello("rete o risposta illeggibile: timed out", codice="rete")):
            def guasto(m, errore=errore):
                raise errore
            ok, testo = ca.commenta(*self.ARGS, chiama=guasto)
            self.assertFalse(ok)
            self.assertNotIn("HTTP", testo)
            self.assertNotIn("timed out", testo)
            self.assertIn("/analisi", testo)

    def test_html_sicuro_e_markdown_tolto(self):
        ok, testo = ca.commenta(*self.ARGS, chiama=lambda m: "<think>ragiono</think>**Fase normale** & <b>tranquilla</b>." + RIEMPITIVO)
        self.assertTrue(ok, testo)
        self.assertNotIn("ragiono", testo)
        self.assertNotIn("**", testo)
        self.assertIn("&amp;", testo)
        self.assertIn("&lt;b&gt;", testo)


class Completezza(unittest.TestCase):
    ARGS = Flusso.ARGS

    def test_testo_troncato_si_riconosce(self):
        problemi = ca.controlla("Il mercato è in fase normale. I due termometri", FONTE)
        self.assertTrue(any("troppo corto" in p for p in problemi), problemi)
        self.assertTrue(any("interrotto" in p for p in problemi), problemi)

    def test_segnale_di_troncamento_poi_riscrive(self):
        risposte = iter([ca.RispostaTroncata("Il mercato è in fase normale. I due termometri"),
                         lungo("Il mercato è in fase normale.")])

        def finto(messaggi):
            r = next(risposte)
            if isinstance(r, Exception):
                raise r
            return r
        ok, testo = ca.commenta(*self.ARGS, chiama=finto)
        self.assertTrue(ok, testo)
        self.assertNotIn("I due termometri", testo)

    def test_finish_reason_length_diventa_troncata(self):
        def apri(req, timeout):
            return _Risposta(json.dumps({"choices": [{"message": {"content": "a metà"},
                                                      "finish_reason": "length"}]}).encode())
        with self.assertRaises(ca.RispostaTroncata):
            ca.chiama_modello([{"role": "user", "content": "x"}], "https://x/v1/chat/completions", "m", "K", _apri=apri)

    def test_gemini_ragiona_poco(self):
        visto = {}

        def apri(req, timeout):
            visto["corpo"] = json.loads(req.data)
            return _Risposta(json.dumps({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}).encode())
        ca.chiama_modello([{"role": "user", "content": "x"}],
                          "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "g", "K", _apri=apri)
        self.assertEqual(visto["corpo"]["reasoning_effort"], "low")
        self.assertGreaterEqual(visto["corpo"]["max_tokens"], 4000)


class _Risposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Chiamata(unittest.TestCase):
    MSG = [{"role": "system", "content": "regole"}, {"role": "user", "content": "report"}]

    def test_formato_openai(self):
        visto = {}

        def apri(req, timeout):
            visto["h"], visto["corpo"] = dict(req.header_items()), json.loads(req.data)
            return _Risposta(json.dumps({"choices": [{"message": {"content": "ciao"}}]}).encode())
        self.assertEqual(ca.chiama_modello(self.MSG, "https://x/v1/chat/completions", "m", "K", _apri=apri), "ciao")
        self.assertEqual(visto["h"]["Authorization"], "Bearer K")
        self.assertEqual(visto["corpo"]["messages"][0]["role"], "system")

    def test_formato_anthropic(self):
        visto = {}

        def apri(req, timeout):
            visto["h"], visto["corpo"] = dict(req.header_items()), json.loads(req.data)
            return _Risposta(json.dumps({"content": [{"type": "text", "text": "ciao"}]}).encode())
        self.assertEqual(ca.chiama_modello(self.MSG, "https://api.anthropic.com/v1/messages", "m", "K", _apri=apri), "ciao")
        self.assertEqual(visto["h"]["X-api-key"], "K")
        self.assertEqual(visto["corpo"]["system"], "regole")
        self.assertTrue(all(m["role"] != "system" for m in visto["corpo"]["messages"]))

    def test_perplexity_senza_ricerca_web(self):
        visto = {}

        def apri(req, timeout):
            visto["corpo"] = json.loads(req.data)
            return _Risposta(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())
        ca.chiama_modello(self.MSG, "https://api.perplexity.ai/chat/completions", "sonar", "K", _apri=apri)
        self.assertIs(visto["corpo"]["disable_search"], True)

    def test_parametri_rifiutati_riprova_minimo(self):
        corpi = []

        def apri(req, timeout):
            corpi.append(json.loads(req.data))
            if len(corpi) == 1:
                raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"unsupported: max_tokens"))
            return _Risposta(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())
        self.assertEqual(ca.chiama_modello(self.MSG, "https://x/v1/chat/completions", "m", "K", _apri=apri), "ok")
        self.assertIn("max_tokens", corpi[0])
        self.assertNotIn("max_tokens", corpi[1])

    def test_la_chiave_non_esce_negli_errori(self):
        def apri(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b"invalid key SEGRETA123"))
        with self.assertRaises(ca.ErroreModello) as e:
            ca.chiama_modello(self.MSG, "https://x/v1/chat/completions", "m", "SEGRETA123", _apri=apri)
        self.assertNotIn("SEGRETA123", str(e.exception))


class Comando(unittest.TestCase):
    """Il comando vero, su un database costruito dai CSV in una cartella temporanea."""

    @classmethod
    def setUpClass(cls):
        from bot import comandi, config
        from botbtc import store
        cls.comandi, cls.config = comandi, config
        cls.cartella = tempfile.mkdtemp()
        cls.conn = store.apri(os.path.join(cls.cartella, "prova.sqlite3"))
        store.bootstrap_da_csv(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.cartella, ignore_errors=True)

    def setUp(self):
        self.salvati = (self.config.LLM_URL, self.config.LLM_MODELLO, self.config.LLM_CHIAVE, ca.chiama_modello)

    def tearDown(self):
        self.config.LLM_URL, self.config.LLM_MODELLO, self.config.LLM_CHIAVE, ca.chiama_modello = self.salvati

    def test_con_maiuscole_e_numeri_veri_del_report(self):
        self.config.LLM_URL, self.config.LLM_MODELLO, self.config.LLM_CHIAVE = "https://x/v1/chat/completions", "m", "K"

        def finto(messaggi, *a, **k):          # un modello onesto: ripete il prezzo del report com'è
            prezzo = re.search(r"Prezzo · ([\d.]+) \$", messaggi[1]["content"]).group(1)
            return lungo(f"Oggi Bitcoin vale {prezzo} dollari e il bot resta sul versamento ricorrente.")
        ca.chiama_modello = finto
        testo = self.comandi.gestisci(self.conn, "/Ai_commentary")
        self.assertIn("il commento di oggi", testo, testo)
        self.assertIn("versamento ricorrente", testo)

    def test_ogni_comando_del_menu_esiste(self):
        """Il menu e i comandi devono restare allineati: niente voci nel menu che il bot non conosce."""
        from bot import telegram_client
        ca.chiama_modello = lambda *a, **k: lungo("Il mercato è in fase normale.")
        self.config.LLM_URL, self.config.LLM_MODELLO, self.config.LLM_CHIAVE = "https://x", "m", "K"
        nomi = [nome for nome, _ in telegram_client.MENU_COMANDI]
        self.assertIn("ai_commentary", nomi)
        for nome in nomi:
            testo = self.comandi.gestisci(self.conn, "/" + nome)
            self.assertNotIn("Non conosco questo comando", testo, nome)
        self.comandi.gestisci(self.conn, "/riprendi")          # non lasciare il database di prova in pausa

    def test_una_volta_al_giorno_per_gli_altri_non_per_te(self):
        from botbtc import store as _store
        self.config.LLM_URL, self.config.LLM_MODELLO, self.config.LLM_CHIAVE = "https://x", "m", "K"
        chiamate = []
        ca.chiama_modello = lambda *a, **k: chiamate.append(1) or lungo("Il mercato è in fase normale.")
        self.comandi.autorizza(self.conn, "777")
        _store.scrivi_impostazione(self.conn, "ai_commentary_777", "")
        self.assertIn("il commento di oggi", self.comandi.gestisci(self.conn, "/ai_commentary", chat_id="777"))
        secondo = self.comandi.gestisci(self.conn, "/ai_commentary", chat_id="777")
        self.assertIn("il prossimo da domani", secondo)
        self.assertEqual(len(chiamate), 1, "il secondo non deve nemmeno chiamare il modello")
        io = self.comandi.padrone()
        for _ in range(3):                                   # il proprietario: nessun limite
            self.assertIn("il commento di oggi", self.comandi.gestisci(self.conn, "/ai_commentary", chat_id=io))
        _store.scrivi_impostazione(self.conn, "ai_commentary_777", "2020-01-01|1")   # un altro giorno
        self.assertIn("il commento di oggi", self.comandi.gestisci(self.conn, "/ai_commentary", chat_id="777"))
        self.comandi.revoca(self.conn, "777")

    def test_un_commento_fallito_non_consuma_il_giorno(self):
        from botbtc import store as _store
        self.config.LLM_URL, self.config.LLM_MODELLO, self.config.LLM_CHIAVE = "https://x", "m", "K"
        self.comandi.autorizza(self.conn, "778")
        _store.scrivi_impostazione(self.conn, "ai_commentary_778", "")

        def guasto(*a, **k):
            raise ca.ErroreModello("HTTP 503")
        ca.chiama_modello = guasto
        ca.ATTESA_SE_OCCUPATO = 0
        self.assertIn("molto richiesta", self.comandi.gestisci(self.conn, "/ai_commentary", chat_id="778"))
        ca.chiama_modello = lambda *a, **k: lungo("Il mercato è in fase normale.")
        self.assertIn("il commento di oggi", self.comandi.gestisci(self.conn, "/ai_commentary", chat_id="778"))
        self.comandi.revoca(self.conn, "778")

    def test_non_configurato(self):
        self.config.LLM_URL = None
        testo = self.comandi.gestisci(self.conn, "/ai_commentary")
        self.assertIn("non è configurato", testo)


if __name__ == "__main__":
    unittest.main()
