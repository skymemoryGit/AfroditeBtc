"""Il tubo verso Telegram (F4.1 del piano).

Scelta implementativa, con la sua ragione (vedi D31):
- **l'invio del report quotidiano usa la sola libreria standard** (`urllib`). E' una POST HTTPS:
  farla dipendere da una libreria esterna significherebbe che il messaggio piu' importante del
  progetto puo' rompersi per un aggiornamento di pacchetto o un venv non attivato sul VPS;
- **i comandi interattivi** (`/analisi`, `/stato`, ...) useranno `python-telegram-bot` (D21), che
  per il long-polling e le tastiere fa risparmiare parecchio codice. E' la parte che, se si rompe,
  non impedisce al report di arrivare.

Regole rispettate qui:
- il token non viene mai stampato, nemmeno negli errori (viene oscurato);
- gli errori di rete non sollevano eccezioni verso il chiamante: tornano come esito, perche' il
  bot deve poter registrare "non sono riuscito a mandare" invece di morire dentro un cron.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{metodo}"
LIMITE_TELEGRAM = 4096


class EsitoInvio:
    """Com'e' andata: `ok` vero/falso, piu' il motivo leggibile se e' andata male."""

    def __init__(self, ok, motivo=None, message_id=None):
        self.ok = ok
        self.motivo = motivo
        self.message_id = message_id

    def __bool__(self):
        return self.ok

    def __repr__(self):
        return f"<invio {'riuscito' if self.ok else 'fallito'}{'' if self.ok else ': ' + str(self.motivo)}>"


def _oscura(testo, token):
    """Il token non deve finire nei log nemmeno per sbaglio."""
    return testo.replace(token, "***TOKEN***") if token else testo


def _chiama(token, metodo, parametri=None, timeout=20):
    url = API.format(token=token, metodo=metodo)
    dati = urllib.parse.urlencode(parametri or {}).encode("utf-8")
    richiesta = urllib.request.Request(url, data=dati if parametri else None,
                                       headers={"User-Agent": "botbtc/1.0"})
    try:
        with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
            corpo = json.loads(risposta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            corpo = json.loads(exc.read().decode("utf-8"))
            return False, f"Telegram ha risposto {exc.code}: {corpo.get('description', '')}"
        except Exception:
            return False, f"Telegram ha risposto {exc.code}"
    except urllib.error.URLError as exc:
        return False, _oscura(f"rete non raggiungibile ({exc.reason})", token)
    except TimeoutError:
        return False, f"timeout dopo {timeout}s"
    except json.JSONDecodeError:
        return False, "risposta non JSON"
    if not corpo.get("ok"):
        return False, f"Telegram ha rifiutato: {corpo.get('description', 'motivo non dato')}"
    return True, corpo.get("result")


def chi_sono(token, timeout=20):
    """Verifica che il token sia valido. Ritorna (ok, descrizione)."""
    ok, risultato = _chiama(token, "getMe", timeout=timeout)
    if not ok:
        return False, risultato
    return True, f"{risultato.get('first_name')} (@{risultato.get('username')})"


def chat_disponibili(token, timeout=20):
    """Chat che hanno scritto al bot: serve a trovare il chat_id la prima volta.

    Telegram non permette di scoprire il proprio id in altro modo: qualcuno deve aver scritto
    al bot almeno una volta. Ritorna (ok, [(chat_id, nome, tipo)]) senza mai stampare il token.
    """
    ok, risultato = _chiama(token, "getUpdates", timeout=timeout)
    if not ok:
        return False, risultato
    viste, fuori = set(), []
    for aggiornamento in risultato or []:
        messaggio = aggiornamento.get("message") or aggiornamento.get("channel_post") or {}
        chat = messaggio.get("chat") or {}
        if chat.get("id") and chat["id"] not in viste:
            viste.add(chat["id"])
            nome = chat.get("first_name") or chat.get("title") or "senza nome"
            fuori.append((chat["id"], nome, chat.get("type")))
    return True, fuori


def aggiornamenti(token, offset=0, timeout_attesa=30, timeout=45):
    """Long polling: resta in attesa fino a `timeout_attesa` secondi e ritorna i messaggi nuovi.

    Ritorna (ok, lista) — `lista` e' [(update_id, chat_id, testo)]. Non solleva eccezioni.
    """
    ok, risultato = _chiama(token, "getUpdates",
                            {"offset": offset, "timeout": timeout_attesa}, timeout=timeout)
    if not ok:
        return False, risultato
    fuori = []
    for aggiornamento in risultato or []:
        messaggio = aggiornamento.get("message") or {}
        chat = (messaggio.get("chat") or {}).get("id")
        testo = messaggio.get("text")
        if chat and testo:
            fuori.append((aggiornamento["update_id"], chat, testo.strip()))
        elif aggiornamento.get("update_id"):
            fuori.append((aggiornamento["update_id"], None, None))
    return True, fuori


def spezza(testo, limite=LIMITE_TELEGRAM):
    """Se un messaggio supera il limite di Telegram lo taglia sui paragrafi, non a meta' parola."""
    if len(testo) <= limite:
        return [testo]
    pezzi, corrente = [], ""
    for paragrafo in testo.split("\n\n"):
        if len(corrente) + len(paragrafo) + 2 > limite:
            if corrente:
                pezzi.append(corrente.rstrip())
            corrente = ""
            while len(paragrafo) > limite:
                pezzi.append(paragrafo[:limite - 1] + "…")
                paragrafo = paragrafo[limite - 1:]
        corrente += paragrafo + "\n\n"
    if corrente.strip():
        pezzi.append(corrente.rstrip())
    return pezzi


def escape_html(testo):
    """Il minimo indispensabile per il parse_mode HTML di Telegram."""
    return testo.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def invia(token, chat_id, testo, timeout=20, anteprima_link=False, formato="HTML"):
    """Manda un messaggio. Non solleva eccezioni: ritorna un EsitoInvio.

    `formato` e' il parse_mode di Telegram ("HTML" o None). Se Telegram rifiuta il markup
    (tag sbagliato, entita' non chiusa) si **riprova in testo semplice**: meglio un messaggio
    brutto che nessun messaggio.
    """
    if not token:
        return EsitoInvio(False, "token mancante: metti BOTBTC_TELEGRAM_TOKEN in bot/.env")
    if not chat_id:
        return EsitoInvio(False, "chat_id mancante: scrivi una volta al bot e rilancia --telegram-chat")
    ultimo_id = None
    for pezzo in spezza(testo):
        parametri = {"chat_id": chat_id, "text": pezzo,
                     "disable_web_page_preview": "false" if anteprima_link else "true"}
        if formato:
            parametri["parse_mode"] = formato
        ok, risultato = _chiama(token, "sendMessage", parametri, timeout=timeout)
        if not ok and formato:
            # markup rifiutato: riprovo senza, spogliando i tag
            import re as _re
            parametri.pop("parse_mode")
            parametri["text"] = _re.sub(r"<[^>]+>", "", pezzo)
            ok, risultato = _chiama(token, "sendMessage", parametri, timeout=timeout)
        if not ok:
            return EsitoInvio(False, risultato)
        ultimo_id = (risultato or {}).get("message_id")
    return EsitoInvio(True, message_id=ultimo_id)


MENU_COMANDI = [
    ("analisi", "Il report completo di oggi"),
    ("stato", "Due righe: dove siamo adesso"),
    ("perche", "Perché siamo in questo stato"),
    ("guida", "Come si legge il report"),
    ("silenzioso", "Scrivimi solo quando cambia lo stato"),
    ("quotidiano", "Torna al battito di ogni giorno"),
    ("registro", "Le ultime giornate"),
    ("pausa", "Sospendi i messaggi"),
    ("riprendi", "Riattiva i messaggi"),
    ("id", "Il tuo identificativo Telegram"),
]


def registra_menu(token, comandi=None, timeout=20):
    """Registra il menu che Telegram mostra digitando "/" (setMyCommands).

    Va fatto una volta sola (e ogni volta che l'elenco cambia): Telegram lo ricorda lato suo.
    """
    import json as _json

    elenco = [{"command": nome, "description": descrizione}
              for nome, descrizione in (comandi or MENU_COMANDI)]
    ok, risultato = _chiama(token, "setMyCommands",
                            {"commands": _json.dumps(elenco, ensure_ascii=False)}, timeout=timeout)
    return (True, f"{len(elenco)} comandi registrati") if ok else (False, risultato)


BENVENUTO = (
    "<b>AphroditeBTC</b> — <i>Love the asset. Analyze the market.</i>\n\n"
    "Guardo Bitcoin ogni giorno al posto tuo e ti dico in che fase siamo:\n"
    "· STRAORDINARIO — fase rara ed economica: varrebbe versare più del solito, in più colpi\n"
    "· normale — nessun estremo: il ricorrente e basta\n"
    "· FRENO — fase cara da mesi: nessun versamento extra\n\n"
    "Non compro e non vendo niente, e non ti dirò mai di vendere: eseguí tu, a mano.\n"
    "Ogni messaggio dice con quali dati ho deciso e di che giorno sono."
)
