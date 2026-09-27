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


def _chi(utente):
    """Identificativo e nome leggibile di chi scrive ("Mario Rossi @mario")."""
    utente = utente or {}
    nome = " ".join(x for x in (utente.get("first_name"), utente.get("last_name")) if x)
    if utente.get("username"):
        nome = (nome + " " if nome else "") + "@" + utente["username"]
    return {"utente_id": utente.get("id"), "nome": nome or None}


def eventi(token, offset=0, timeout_attesa=30, timeout=45):
    """Come `aggiornamenti`, ma riconosce anche i tocchi sui pulsanti (callback_query) e chi scrive.

    Ritorna (ok, lista di dict). Ogni evento ha update_id e tipo: "messaggio" (con chat_id, testo,
    utente_id, nome), "pulsante" (con chat_id, message_id, callback_id, dati, utente_id, nome) oppure
    None per tutto il resto, che va solo saltato. Non solleva eccezioni.
    """
    ok, risultato = _chiama(token, "getUpdates",
                            {"offset": offset, "timeout": timeout_attesa}, timeout=timeout)
    if not ok:
        return False, risultato
    fuori = []
    for aggiornamento in risultato or []:
        evento = {"update_id": aggiornamento.get("update_id"), "tipo": None}
        if aggiornamento.get("message"):
            m = aggiornamento["message"]
            evento.update(tipo="messaggio" if m.get("text") else None,
                          chat_id=(m.get("chat") or {}).get("id"),
                          testo=(m.get("text") or "").strip(), **_chi(m.get("from")))
        elif aggiornamento.get("callback_query"):
            q = aggiornamento["callback_query"]
            m = q.get("message") or {}
            evento.update(tipo="pulsante", chat_id=(m.get("chat") or {}).get("id"),
                          message_id=m.get("message_id"), callback_id=q.get("id"),
                          dati=q.get("data") or "", **_chi(q.get("from")))
        fuori.append(evento)
    return True, fuori


def rispondi_pulsante(token, callback_id, avviso=None, timeout=20):
    """Conferma a Telegram il tocco su un pulsante (senza, il pulsante resta "in caricamento")."""
    parametri = {"callback_query_id": callback_id}
    if avviso:
        parametri["text"] = avviso
    return _chiama(token, "answerCallbackQuery", parametri, timeout=timeout)


def modifica(token, chat_id, message_id, testo, reply_markup=None, timeout=20):
    """Riscrive un messaggio già mandato. Senza reply_markup i pulsanti spariscono."""
    parametri = {"chat_id": chat_id, "message_id": message_id, "text": testo, "parse_mode": "HTML"}
    if reply_markup is not None:
        parametri["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return _chiama(token, "editMessageText", parametri, timeout=timeout)


def invia(token, chat_id, testo, timeout=20, anteprima_link=False, formato="HTML", reply_markup=None):
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
    pezzi = spezza(testo)
    for numero, pezzo in enumerate(pezzi):
        parametri = {"chat_id": chat_id, "text": pezzo,
                     "disable_web_page_preview": "false" if anteprima_link else "true"}
        if reply_markup is not None and numero == len(pezzi) - 1:     # i pulsanti sull'ultimo pezzo
            parametri["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
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
    ("stato", "Com'è il mercato oggi, in breve"),
    ("analisi", "Tutti i numeri di oggi"),
    ("perche", "Come ho deciso la fase di oggi"),
    ("ai_commentary", "L'analisi raccontata a parole (AI)"),
    ("guida", "Come si leggono i messaggi"),
    ("quotidiano", "Un messaggio breve ogni mattina"),
    ("silenzioso", "Scrivimi solo quando cambia la fase"),
    ("pausa", "Ferma tutti i messaggi"),
    ("riprendi", "Riattiva i messaggi"),
    ("registro", "Le ultime giornate"),
    ("id", "Il tuo ID Telegram"),
]


# Il proprietario vede anche la gestione degli accessi. Gli altri autorizzati NO: non devono nemmeno sapere
# che esiste. Gli sconosciuti non vedono nessun menu.
MENU_PADRONE = MENU_COMANDI + [
    ("autorizza", "Dai accesso a una persona"),
    ("revoca", "Togli l'accesso a una persona"),
    ("utenti", "Chi può usare il bot"),
]


def _scope_chat(chat_id):
    return json.dumps({"type": "chat", "chat_id": int(chat_id)})


def sincronizza_menu(token, padrone, autorizzati, rimossi=(), timeout=20):
    """Chi vede quale menu digitando "/":

    - sconosciuti: nessun menu (si cancella quello generale: meno informazioni possibile);
    - autorizzati: i comandi del report (MENU_COMANDI);
    - proprietario: gli stessi più /autorizza, /revoca, /utenti (MENU_PADRONE);
    - chi è stato appena revocato: il suo menu si cancella.
    Si rifà a ogni avvio dell'ascolto e a ogni cambio degli accessi. Ritorna (ok, descrizione).
    """
    problemi = []
    for scope in (None, {"type": "all_private_chats"}):
        ok, risultato = _chiama(token, "deleteMyCommands",
                                {"scope": json.dumps(scope)} if scope else {"scope": json.dumps({"type": "default"})},
                                timeout=timeout)
        if not ok:
            problemi.append(f"menu generale: {risultato}")
    persone = 0
    for chat in sorted({str(x) for x in autorizzati} | ({str(padrone)} if padrone else set())):
        voci = MENU_PADRONE if chat == str(padrone) else MENU_COMANDI
        elenco = json.dumps([{"command": n, "description": d} for n, d in voci], ensure_ascii=False)
        ok, risultato = _chiama(token, "setMyCommands", {"commands": elenco, "scope": _scope_chat(chat)},
                                timeout=timeout)
        if ok:
            persone += 1
        else:
            problemi.append(f"{chat}: {risultato}")
    for chat in rimossi:
        ok, risultato = _chiama(token, "deleteMyCommands", {"scope": _scope_chat(chat)}, timeout=timeout)
        if not ok:
            problemi.append(f"{chat}: {risultato}")
    esito = f"menu per {persone} {'persona' if persone == 1 else 'persone'}, nessuno per gli sconosciuti"
    return (not problemi), esito + (" — problemi: " + "; ".join(problemi) if problemi else "")


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
    "₿ <b>AphroditeBTC</b>\n<i>Love the asset. Analyze the market.</i>\n\n"
    "Guardo Bitcoin ogni giorno al posto tuo e ti dico in che fase siamo:\n\n"
    "🟢 <b>Straordinario</b> — prezzi bassi come capita di rado: vale la pena mettere qualcosa in più\n"
    "⚪️ <b>Normale</b> — niente di speciale: bastano i soliti versamenti\n"
    "🟠 <b>Caldo</b> — prezzi alti: niente extra\n"
    "🔴 <b>Freno</b> — caro da mesi: niente extra\n\n"
    "Non compro e non vendo niente, e non ti dirò mai di vendere: decidi ed esegui tu.\n"
    "<i>Ogni messaggio dice di che giorno sono i dati.</i>"
)
