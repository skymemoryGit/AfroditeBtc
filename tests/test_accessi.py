"""Accessi gestiti da Telegram (D45) — tutto offline, con un Telegram finto.

    python3 -m unittest tests.test_accessi -v

Richieste dell'utente: allo sconosciuto solo "This is a private bot" e il suo ID; /autorizza dal menu chiede
l'ID; /revoca mostra l'elenco a pulsanti con Annulla; /autorizza, /revoca e /utenti solo nel menu del
proprietario; gli sconosciuti nessun menu.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import comandi, config, telegram_client
from botbtc import store


class Base(unittest.TestCase):
    def setUp(self):
        self.cartella = tempfile.mkdtemp()
        self.conn = store.apri(os.path.join(self.cartella, "p.sqlite3"))
        self.io = comandi.padrone() or "999"
        if not comandi.padrone():
            self.skipTest("serve BOTBTC_TELEGRAM_CHAT_ID in bot/.env")

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.cartella, ignore_errors=True)

    def dico(self, testo, chi=None):
        return comandi.gestisci(self.conn, testo, chat_id=chi or self.io)


class Sconosciuto(Base):
    def test_vede_solo_private_bot_e_il_suo_id(self):
        for testo in ("/start", "/analisi", "/ai_commentary", "/id", "/revoca", "ciao", "123456"):
            risposta = self.dico(testo, "555")
            self.assertEqual(risposta, "This is a private bot.\nYour ID: <code>555</code>", testo)

    def test_non_puo_autorizzarsi_mandando_numeri(self):
        self.dico("555", "555")
        self.dico("/autorizza 555", "555")
        self.assertNotIn("555", comandi.autorizzati(self.conn))


class Autorizza(Base):
    def test_dal_menu_chiede_l_id_e_poi_autorizza(self):
        domanda = self.dico("/autorizza")
        self.assertIsInstance(domanda, dict)
        self.assertIn("ID", domanda["testo"])
        self.assertTrue(domanda["reply_markup"]["force_reply"])
        esito = self.dico("555000111")
        self.assertIn("555000111", esito)
        self.assertIn("555000111", comandi.autorizzati(self.conn))
        self.assertNotIn("private bot", self.dico("/id", "555000111"))

    def test_si_risponde_una_volta_sola(self):
        self.dico("/autorizza")
        self.dico("555")
        self.dico("666")                                # nessuna domanda aperta: non autorizza nessuno
        self.assertNotIn("666", comandi.autorizzati(self.conn))

    def test_risposta_non_numerica(self):
        self.dico("/autorizza")
        self.assertIn("identificativo numerico", self.dico("mario"))
        self.assertEqual(comandi.autorizzati(self.conn), {self.io})

    def test_un_comando_annulla_la_domanda(self):
        self.dico("/autorizza")
        self.assertIn("Chi può usare il bot", self.dico("/utenti"))
        self.dico("777")
        self.assertNotIn("777", comandi.autorizzati(self.conn))

    def test_un_autorizzato_non_puo_aprire_la_domanda(self):
        self.dico("/autorizza 777")
        self.assertIn("Solo il proprietario", self.dico("/autorizza", "777"))
        self.dico("888", "777")
        self.assertNotIn("888", comandi.autorizzati(self.conn))

    def test_forma_rapida_con_il_numero(self):
        self.assertIn("ora può usare il bot", self.dico("/autorizza 777"))


class Revoca(Base):
    def test_elenco_a_pulsanti_con_annulla_e_nomi(self):
        self.dico("/autorizza 777")
        self.dico("/autorizza 888")
        comandi.ricorda_nome(self.conn, "777", "Mario Rossi @mario")
        risposta = self.dico("/revoca")
        pulsanti = risposta["reply_markup"]["inline_keyboard"]
        testi = [riga[0]["text"] for riga in pulsanti]
        self.assertEqual(testi, ["Mario Rossi @mario — 777", "ID 888", "✕ Annulla"])
        self.assertEqual(pulsanti[0][0]["callback_data"], "revoca:777")
        self.assertNotIn(self.io, json.dumps(pulsanti), "il proprietario non si toglie da solo")

    def test_nessuno_da_togliere(self):
        self.assertIn("Non hai autorizzato nessuno", self.dico("/revoca"))

    def test_pulsante_del_proprietario_revoca(self):
        self.dico("/autorizza 777")
        esito = comandi.gestisci_pulsante(self.conn, "revoca:777", self.io)
        self.assertIn("non può più usare", esito["testo"])
        self.assertNotIn("777", comandi.autorizzati(self.conn))

    def test_pulsante_premuto_da_altri_non_fa_niente(self):
        self.dico("/autorizza 777")
        esito = comandi.gestisci_pulsante(self.conn, "revoca:777", "777")
        self.assertIsNone(esito["testo"])
        self.assertIn("777", comandi.autorizzati(self.conn))

    def test_annulla(self):
        self.assertIn("Annullato", comandi.gestisci_pulsante(self.conn, "annulla", self.io)["testo"])

    def test_forma_rapida_con_il_numero(self):
        self.dico("/autorizza 777")
        self.assertIn("non può più usare", self.dico("/revoca 777"))


class Menu(unittest.TestCase):
    def setUp(self):
        self.chiamate = []
        self.originale = telegram_client._chiama
        telegram_client._chiama = lambda token, metodo, parametri=None, timeout=20: (
            self.chiamate.append((metodo, parametri or {}))
            or (True, {"message_id": 1} if metodo == "sendMessage" else True))

    def tearDown(self):
        telegram_client._chiama = self.originale

    def test_menu_per_persona(self):
        ok, _ = telegram_client.sincronizza_menu("T", "100", {"100", "200"}, rimossi=["300"])
        self.assertTrue(ok)
        cancellati = [json.loads(p["scope"])["type"] for m, p in self.chiamate if m == "deleteMyCommands"]
        self.assertIn("default", cancellati)                  # sconosciuti: nessun menu
        self.assertIn("all_private_chats", cancellati)
        menu = {json.loads(p["scope"])["chat_id"]: [c["command"] for c in json.loads(p["commands"])]
                for m, p in self.chiamate if m == "setMyCommands"}
        for solo_tuo in ("autorizza", "revoca", "utenti"):
            self.assertIn(solo_tuo, menu[100])
            self.assertNotIn(solo_tuo, menu[200])            # gli altri non li vedono proprio
        self.assertIn("ai_commentary", menu[200])
        rimosso = [json.loads(p["scope"]) for m, p in self.chiamate
                   if m == "deleteMyCommands" and json.loads(p["scope"]).get("chat_id") == 300]
        self.assertTrue(rimosso, "il menu di chi è revocato si cancella")

    def test_eventi_riconosce_messaggi_e_pulsanti(self):
        telegram_client._chiama = lambda *a, **k: (True, [
            {"update_id": 1, "message": {"chat": {"id": 5}, "text": " /stato ",
                                         "from": {"id": 5, "first_name": "Mario", "username": "mario"}}},
            {"update_id": 2, "callback_query": {"id": "cb", "data": "revoca:7", "from": {"id": 9},
                                                "message": {"message_id": 44, "chat": {"id": 9}}}},
            {"update_id": 3, "edited_message": {}}])
        ok, eventi = telegram_client.eventi("T")
        self.assertEqual([e["tipo"] for e in eventi], ["messaggio", "pulsante", None])
        self.assertEqual((eventi[0]["testo"], eventi[0]["nome"]), ("/stato", "Mario @mario"))
        self.assertEqual((eventi[1]["dati"], eventi[1]["message_id"], eventi[1]["callback_id"]), ("revoca:7", 44, "cb"))

    def test_invia_con_pulsanti(self):
        telegram_client.invia("T", 5, "scegli", reply_markup={"inline_keyboard": [[{"text": "a", "callback_data": "x"}]]})
        metodo, parametri = self.chiamate[-1]
        self.assertEqual(metodo, "sendMessage")
        self.assertEqual(json.loads(parametri["reply_markup"])["inline_keyboard"][0][0]["callback_data"], "x")


class GiroDiAscolto(unittest.TestCase):
    """Un giro dell'ascolto vero, con Telegram finto: sconosciuto, /revoca, tocco sul pulsante."""

    def test_un_giro(self):
        io = comandi.padrone()
        if not io:
            self.skipTest("serve BOTBTC_TELEGRAM_CHAT_ID in bot/.env")
        cartella = tempfile.mkdtemp()
        db = os.path.join(cartella, "p.sqlite3")
        conn = store.apri(db)
        comandi.autorizza(conn, "777")
        conn.close()
        inviati, modificati, menu = [], [], []
        originali = {n: getattr(telegram_client, n) for n in ("eventi", "invia", "rispondi_pulsante",
                                                              "modifica", "sincronizza_menu")}
        telegram_client.eventi = lambda *a, **k: (True, [
            {"update_id": 10, "tipo": "messaggio", "chat_id": 555, "utente_id": 555, "nome": "Sconosciuto", "testo": "/analisi"},
            {"update_id": 11, "tipo": "messaggio", "chat_id": int(io), "utente_id": int(io), "nome": "Io", "testo": "/revoca"},
            {"update_id": 12, "tipo": "pulsante", "chat_id": int(io), "utente_id": int(io), "nome": "Io",
             "dati": "revoca:777", "callback_id": "c1", "message_id": 99}])
        telegram_client.invia = lambda token, chat, testo, **k: inviati.append((chat, testo, k.get("reply_markup"))) or True
        telegram_client.rispondi_pulsante = lambda *a, **k: (True, True)
        telegram_client.modifica = lambda token, chat, mid, testo, **k: modificati.append(testo) or (True, True)
        telegram_client.sincronizza_menu = lambda token, padrone, aut, rimossi=(): menu.append(sorted(rimossi)) or (True, "ok")
        sorprese_prima, config.PING_PER_SETTIMANA = config.PING_PER_SETTIMANA, 0   # questo test non va in rete
        try:
            comandi.ascolta(db, giri=1)
        finally:
            config.PING_PER_SETTIMANA = sorprese_prima
            for n, f in originali.items():
                setattr(telegram_client, n, f)
            shutil.rmtree(cartella, ignore_errors=True)
        self.assertEqual(inviati[0][1], "This is a private bot.\nYour ID: <code>555</code>")
        self.assertIn("revoca:777", json.dumps(inviati[1][2]))
        self.assertIn("non può più usare", modificati[0])
        self.assertEqual(menu[-1], ["777"])                   # menu ricalcolati, quello di 777 cancellato


if __name__ == "__main__":
    unittest.main()
