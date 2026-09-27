"""I comandi di Telegram (F4.2 del piano).

Scelta implementativa: **long polling con la sola libreria standard**, non `python-telegram-bot`.
Precisa ulteriormente D21/D31: i comandi sono sei, il ciclo di ascolto sta in un centinaio di
righe, e cosi' sul VPS non serve alcun venv — una dipendenza in meno da aggiornare e da rompere.
Se un giorno servissero tastiere, bottoni o conversazioni a piu' passi, si riapre la scelta.

Comandi:
  /start      chi sono e cosa faccio
  /guida      come si legge il report (da fissare in chat)
  /analisi    il report completo, adesso
  /stato      il polso, due righe
  /perche     perche' oggi lo stato e' quello
  /silenzioso solo i cambi di stato (niente battito quotidiano)
  /quotidiano torna a ricevere il polso tutti i giorni
  /pausa      non mandarmi piu' niente
  /riprendi   ricomincia
  /registro   le ultime giornate registrate

Regole: risponde **solo** al chat_id configurato (e' un bot personale), non esegue ordini, e se
una cosa non la sa lo dice.
"""

import datetime
import html
import json
import time

from bot import commento_ai, config, sorprese, telegram_client
from botbtc import dataset, engine, messaggi, sanity, store

AIUTO = ("Comandi:\n"
         "/analisi — il report completo di oggi\n"
         "/stato — due righe, al volo\n"
         "/perche — perché oggi siamo in questo stato\n"
         "/ai_commentary — il report di oggi spiegato a parole da un modello AI (uno al giorno)\n"
         "/guida — come si legge il report\n"
         "/silenzioso — scrivimi solo quando cambia lo stato\n"
         "/quotidiano — torna al battito di ogni giorno\n"
         "/pausa e /riprendi — sospendi o riattiva tutto\n"
         "/registro — le ultime giornate\n"
         "/id — il tuo identificativo Telegram")

AIUTO_PADRONE = ("\n\n<b>Solo per te</b>\n"
                 "/utenti — chi può usare il bot\n"
                 "/autorizza — dai accesso a qualcuno (ti chiedo l'ID)\n"
                 "/revoca — togli l'accesso (scegli dall'elenco)")

# Tutto quello che vede chi non è autorizzato: niente altro, nemmeno cosa fa il bot (richiesta dell'utente).
PRIVATO = "This is a private bot.\nYour ID: <code>{chi}</code>"


# ------------------------------------------------------------ autorizzazioni

def padrone():
    """Il proprietario del bot: il chat_id in bot/.env. Non si puo' revocare."""
    return str(config.TELEGRAM_CHAT_ID or "")


def autorizzati(conn):
    """Insieme dei chat_id che possono usare il bot: il padrone piu' quelli aggiunti a mano."""
    salvati = store.leggi_impostazione(conn, "autorizzati", "") or ""
    insieme = {x.strip() for x in salvati.split(",") if x.strip()}
    if padrone():
        insieme.add(padrone())
    return insieme


def _nomi(conn):
    try:
        return json.loads(store.leggi_impostazione(conn, "nomi_utenti", "") or "{}")
    except ValueError:
        return {}


def ricorda_nome(conn, chat_id, nome):
    """Il nome con cui una persona compare su Telegram, per riconoscerla negli elenchi (solo nel database)."""
    if not chat_id or not nome:
        return
    nomi = _nomi(conn)
    if nomi.get(str(chat_id)) != nome:
        nomi[str(chat_id)] = nome
        store.scrivi_impostazione(conn, "nomi_utenti", json.dumps(nomi, ensure_ascii=False))


def etichetta(conn, chat_id):
    """"Mario Rossi @mario — 123456789", oppure solo l'ID se la persona non ha ancora scritto al bot."""
    nome = _nomi(conn).get(str(chat_id))
    return f"{nome} — {chat_id}" if nome else f"ID {chat_id}"


def _autorizza_id(conn, argomento):
    if not argomento.lstrip("-").isdigit():
        return ("Serve un identificativo numerico, per esempio <code>123456789</code>. "
                "Tocca di nuovo /autorizza per riprovare.")
    autorizza(conn, argomento)
    return (f"✅ {html.escape(etichetta(conn, argomento))} ora può usare il bot.\n"
            "<i>Riceverà le risposte ai comandi, non il report quotidiano: quello resta tuo.</i>")


def autorizza(conn, chat_id):
    insieme = autorizzati(conn) | {str(chat_id).strip()}
    store.scrivi_impostazione(conn, "autorizzati", ",".join(sorted(insieme)))
    return insieme


def revoca(conn, chat_id):
    chat_id = str(chat_id).strip()
    if chat_id == padrone():
        return None                       # il padrone non si toglie da solo per sbaglio
    insieme = autorizzati(conn) - {chat_id}
    store.scrivi_impostazione(conn, "autorizzati", ",".join(sorted(insieme)))
    return insieme


def _contesto(conn, serie="coinbase"):
    """Dataset + stati, ricalcolati al momento. Circa 7 secondi: accettabile per un comando."""
    ds = dataset.carica(conn, serie=serie)
    dataset.aggiungi_percentili(ds, config.FINESTRA_PERCENTILE_GIORNI)
    percentili = [dataset.percentili_del_giorno(ds, i) for i in range(len(ds))]
    valori = [{k: ds.ind.get(k, [None] * len(ds))[i] for k in engine.PESI} for i in range(len(ds))]
    righe = engine.serie_stati(percentili, config.parametri_motore(), valori)
    return ds, righe


def _perche(ds, righe, indice, foto, parametri):
    valutazione = righe[indice]
    stato = valutazione.get("stato_confermato", valutazione["stato"])
    vista = messaggi.vista_stato(valutazione, parametri)
    parti = [f"🔎 <b>Come ho calcolato lo stato di oggi</b>",
             f"Risultato: {vista['icona']} <b>{vista['titolo']}</b> — <i>{vista['spiegazione']}</i>", ""]
    if valutazione["punteggio_economico"] is None:
        parti.append("Non ho abbastanza ingredienti per calcolare i punteggi.")
        return "\n".join(parti)
    parti.append(f"▸ punteggio economico <b>{messaggi._fisso(valutazione['punteggio_economico'])}</b>"
                 f" (serve {messaggi._fisso(parametri.soglia_straordinario)})")
    parti.append(f"▸ punteggio caro <b>{messaggi._fisso(valutazione['punteggio_caro'])}</b>"
                 f" (serve {messaggi._fisso(parametri.soglia_freno)} per almeno "
                 f"{parametri.durata_minima_caro} giorni)")
    parti.append("")
    parti.append("<b>Quanto pesa ogni indicatore oggi</b>")
    parti.append("<i>La barretta è quanto è estremo rispetto ai suoi ultimi 4 anni: "
                 "▯▯▯▯▯ = normale, ▮▮▮▮▮ = come non lo era da 4 anni.</i>")
    contributi = sorted(valutazione["contributi"].items(),
                        key=lambda kv: max(kv[1]["economico"], kv[1]["caro"]) * kv[1]["peso"],
                        reverse=True)
    for chiave, c in contributi:
        modello, decimali = engine.FRASI.get(chiave, ("{v}", 2))
        valore = ds.ind.get(chiave, [None] * len(ds))[indice]
        nome = modello.format(v=messaggi._fisso(valore, decimali)) if valore is not None else chiave
        quota = max(c["economico"], c["caro"])
        verso = "economico" if c["economico"] >= c["caro"] else "caro"
        barretta = "▮" * round(quota * 5) + "▯" * (5 - round(quota * 5))
        nome = nome.replace("&", "&amp;")
        etichetta = ("verso economico" if verso == "economico" else "verso caro") if quota > 0 else "neutro"
        peso = f"{c['peso']:g}".replace(".", ",")
        parti.append(f"{barretta} {nome} <i>({etichetta}, conta {peso} su 1,20)</i>")
        conto = messaggi.quanti_piu_alti(ds, chiave, indice)
        if conto:   # la barretta detta con i giorni veri (D42)
            parti.append("     <i>↳ " + engine.confronto_in_giorni(conto["piu_alti"], conto["totale"],
                                                                  conto["anni"], conto["uguali"]) + "</i>")
    if valutazione.get("ingredienti_mancanti"):
        parti.append("\nMancano oggi: " + ", ".join(messaggi._nome_umano(k)
                                                    for k in valutazione["ingredienti_mancanti"]))
    parti.append("\n<i>Il punteggio è la media di queste barrette, pesata per quanto conta ogni "
                 "indicatore. Si usano i percentili sugli ultimi 4 anni e non soglie fisse, perché le "
                 "soglie fisse invecchiano: l'MVRV ai massimi è passato da 4,43 (2017) a 2,29 (2025).</i>")
    return "\n".join(parti)


def gestisci(conn, comando, serie="coinbase", chat_id=None):
    """Da comando a testo di risposta. Funzione pura rispetto a Telegram: non manda niente.

    `chat_id` serve per le autorizzazioni: il bot e' personale, non un servizio pubblico.
    Chiunque puo' scrivergli (Telegram non lo impedisce), ma risponde davvero solo a chi e'
    in elenco. A tutti gli altri dice il loro identificativo, cosi' possono chiedere l'accesso.
    """
    testo = comando.strip()
    comando = testo.split()[0].split("@")[0].lower() if testo else ""
    argomento = testo.split(maxsplit=1)[1].strip() if len(testo.split()) > 1 else ""
    parametri = config.parametri_motore()
    chi = str(chat_id) if chat_id is not None else padrone()
    e_padrone = chi == padrone()
    ammesso = chi in autorizzati(conn)

    # --- chi non è autorizzato vede solo questo, qualunque cosa scriva (anche /id)
    if not ammesso:
        return PRIVATO.format(chi=chi)
    if comando == "/id":
        return f"Il tuo identificativo Telegram è <code>{chi}</code>.\nSei autorizzato a usare il bot."

    # --- risposta a una domanda del bot (oggi solo: "mandami l'ID da autorizzare")
    chiave_attesa = f"attesa_{chi}"
    attesa = store.leggi_impostazione(conn, chiave_attesa, "") or ""
    if attesa:
        store.scrivi_impostazione(conn, chiave_attesa, "")        # si risponde una volta sola
        if not testo.startswith("/") and attesa == "autorizza" and e_padrone:
            return _autorizza_id(conn, testo.split()[0] if testo else "")
        # un comando qualsiasi annulla la domanda e viene eseguito normalmente

    # --- gestione degli accessi, solo per il padrone (e solo il suo menu la mostra)
    if comando in ("/utenti", "/autorizza", "/revoca"):
        if not e_padrone:
            return "Solo il proprietario del bot può gestire gli accessi."
        if comando == "/utenti":
            righe = ["👥 <b>Chi può usare il bot</b>"]
            for uno in sorted(autorizzati(conn)):
                righe.append("▸ " + html.escape(etichetta(conn, uno))
                             + (" <i>(tu, proprietario)</i>" if uno == padrone() else ""))
            righe.append("\n<i>/autorizza per aggiungere · /revoca per togliere</i>")
            return "\n".join(righe)
        if comando == "/autorizza":
            if not argomento:
                store.scrivi_impostazione(conn, chiave_attesa, "autorizza")
                return {"testo": ("Mandami l'<b>ID</b> della persona da autorizzare.\n"
                                  "<i>Lo trova scrivendo qualunque cosa al bot: gli risponde con il suo ID.</i>"),
                        "reply_markup": {"force_reply": True,
                                         "input_field_placeholder": "ID Telegram, es. 123456789"}}
            return _autorizza_id(conn, argomento)
        if not argomento:                                          # /revoca: elenco a pulsanti
            altri = sorted(autorizzati(conn) - {padrone()})
            if not altri:
                return "Non hai autorizzato nessuno: c'è solo il tuo accesso."
            pulsanti = [[{"text": etichetta(conn, uno), "callback_data": f"revoca:{uno}"}] for uno in altri]
            pulsanti.append([{"text": "✕ Annulla", "callback_data": "annulla"}])
            quante = "una persona ha" if len(altri) == 1 else f"{len(altri)} persone hanno"
            return {"testo": f"A chi vuoi togliere l'accesso? ({quante} accesso oltre a te)",
                    "reply_markup": {"inline_keyboard": pulsanti}}
        if not argomento.lstrip("-").isdigit():
            return f"Serve un identificativo numerico: <code>{comando} 123456789</code>"
        esito = revoca(conn, argomento)
        if esito is None:
            return "Non posso togliere te stesso: sei il proprietario."
        return f"🚫 {html.escape(etichetta(conn, argomento))} non può più usare il bot."

    if comando in ("/start", "/aiuto", "/help"):
        return telegram_client.BENVENUTO + "\n\n" + AIUTO + (AIUTO_PADRONE if e_padrone else "")
    if comando == "/guida":
        return messaggi.guida()
    if comando == "/pausa":
        store.scrivi_impostazione(conn, "pausa", "1")
        return "⏸ Messo in pausa. Non ti scrivo più finché non mandi /riprendi."
    if comando == "/riprendi":
        store.scrivi_impostazione(conn, "pausa", "0")
        return "▶️ Riprendo. Ti scrivo di nuovo ogni giorno."
    if comando == "/silenzioso":
        store.scrivi_impostazione(conn, "modalita", "silenzioso")
        return ("🔕 Modalità silenziosa: ti scrivo <b>solo quando cambia lo stato</b> — per esempio "
                "quando si accende una fase come giugno 2026. Il resto lo registro e basta.\n"
                "Per rivedere il battito quotidiano: /quotidiano")
    if comando == "/quotidiano":
        store.scrivi_impostazione(conn, "modalita", "quotidiano")
        return "🔔 Torno a mandarti il polso tutti i giorni, due righe."
    if comando == "/registro":
        righe = store.righe_registro(conn, 7)
        if not righe:
            return "Il registro è vuoto: si riempie a ogni report."
        fuori = ["📒 <b>Ultime giornate</b>"]
        for r in righe:
            punteggio = "n/d" if r["punteggio_economico"] is None else f"{r['punteggio_economico']:.2f}".replace(".", ",")
            fuori.append(f"▸ {r['data']} · {r['stato']} · punteggio {punteggio} · "
                         f"{r['prezzo']:,.0f} $".replace(",", "."))
        return "\n".join(fuori)

    if comando == "/ai_commentary":
        # il report di oggi (lo stesso di /analisi) raccontato da un modello linguistico, con i numeri
        # controllati sul report prima di mandarlo (D44). Limite al giorno per gli altri, non per te (D47).
        oggi = sorprese.adesso(config.FUSO_UTENTE).date().isoformat()
        chiave_limite = f"ai_commentary_{chi}"
        giorno, _, usati = (store.leggi_impostazione(conn, chiave_limite, "") or "").partition("|")
        usati = int(usati) if giorno == oggi and usati.isdigit() else 0
        if not e_padrone and 0 < config.AI_COMMENTI_AL_GIORNO <= usati:
            return ("Il commento di oggi l'hai già chiesto: il prossimo da domani.\n"
                    "<i>Il report completo resta disponibile con /analisi.</i>")
        if store.conteggi(conn)["prezzi"] == 0:
            return "Non ho ancora dati in archivio."
        ds, righe = _contesto(conn, serie)
        indice = len(ds) - 1
        foto = dataset.fotografia(ds, ds.dates[indice])
        analisi = messaggi.analisi_completa(ds, righe, indice, foto, parametri,
                                            config.BUDGET_MENSILE_EUR, config.TETTO_STRAORDINARIO_MESI)
        riuscito, testo = commento_ai.commenta(analisi, messaggi.guida(), config.BUDGET_MENSILE_EUR,
                                               config.LLM_URL, config.LLM_MODELLO, config.LLM_CHIAVE,
                                               data=foto["data"], timeout=config.LLM_TIMEOUT_SECONDI)
        if riuscito and not e_padrone:           # si consuma solo un commento arrivato davvero
            store.scrivi_impostazione(conn, chiave_limite, f"{oggi}|{usati + 1}")
        return testo

    if comando in ("/analisi", "/stato", "/perche", "/perché"):
        if store.conteggi(conn)["prezzi"] == 0:
            return "Non ho ancora dati in archivio."
        ds, righe = _contesto(conn, serie)
        indice = len(ds) - 1
        foto = dataset.fotografia(ds, ds.dates[indice])
        if comando == "/analisi":
            return messaggi.analisi_completa(ds, righe, indice, foto, parametri,
                                             config.BUDGET_MENSILE_EUR,
                                             config.TETTO_STRAORDINARIO_MESI)
        if comando == "/stato":
            return messaggi.polso(ds, righe, indice, foto, parametri, config.BUDGET_MENSILE_EUR)
        return _perche(ds, righe, indice, foto, parametri)

    return "Non conosco questo comando.\n\n" + AIUTO


def gestisci_pulsante(conn, dati, utente_id):
    """Un tocco su un pulsante. Ritorna {"testo": nuovo testo del messaggio o None, "avviso": notifica breve}.

    Solo il proprietario può usare i pulsanti degli accessi: il controllo si fa qui, sul mittente vero,
    non sul fatto che il pulsante sia comparso solo a lui.
    """
    if str(utente_id) != padrone():
        return {"testo": None, "avviso": "Solo il proprietario."}
    if dati == "annulla":
        return {"testo": "Annullato: nessuna modifica.", "avviso": None}
    if dati.startswith("revoca:"):
        chi = dati.split(":", 1)[1]
        nome = etichetta(conn, chi)
        if revoca(conn, chi) is None:
            return {"testo": "Non posso togliere te stesso: sei il proprietario.", "avviso": None}
        return {"testo": f"🚫 {html.escape(nome)} non può più usare il bot.", "avviso": "Accesso tolto"}
    return {"testo": None, "avviso": "Pulsante non più valido."}


def sincronizza_menu(conn, rimossi=()):
    """Menu per persona (vedi telegram_client.sincronizza_menu). Se fallisce non è grave."""
    return telegram_client.sincronizza_menu(config.TELEGRAM_TOKEN, padrone(), autorizzati(conn), rimossi)


def _manda(chat_id, risposta):
    """Una risposta di gestisci: testo semplice oppure {"testo", "reply_markup"} (pulsanti, domanda)."""
    if isinstance(risposta, dict):
        return telegram_client.invia(config.TELEGRAM_TOKEN, chat_id, risposta["testo"],
                                     timeout=config.TIMEOUT_RETE_SECONDI,
                                     reply_markup=risposta.get("reply_markup"))
    return telegram_client.invia(config.TELEGRAM_TOKEN, chat_id, risposta, timeout=config.TIMEOUT_RETE_SECONDI)


def messaggio_sorpresa(conn, serie="coinbase"):
    """Il polso di oggi con i dati aggiornati, e una riga che dice perché arriva senza che lo chiedessi."""
    try:
        store.aggiorna_da_rete(conn, timeout=config.TIMEOUT_RETE_SECONDI, tentativi=config.TENTATIVI_RETE)
    except Exception as exc:                     # senza rete si usa l'archivio: il polso dichiara le date
        print(f"    aggiornamento dati non riuscito: {exc}")
    ds, righe = _contesto(conn, serie)
    indice = len(ds) - 1
    foto = dataset.fotografia(ds, ds.dates[indice])
    return ("🔔 <i>Sono sveglio: ecco dove siamo.</i>\n"
            + messaggi.polso(ds, righe, indice, foto, config.parametri_motore(), config.BUDGET_MENSILE_EUR))


def controlla_sorprese(conn, serie="coinbase", momento=None, rng=None):
    """Da chiamare a ogni giro dell'ascolto: se è l'ora di un messaggio a sorpresa lo manda (D46).

    Ritorna il testo mandato, o None. Solo al proprietario, come il report; niente se il bot è in pausa o in
    modalità silenziosa, perché lì il silenzio l'ha chiesto lui.
    """
    if config.PING_PER_SETTIMANA <= 0 or not padrone():
        return None
    momento = momento or sorprese.adesso(config.FUSO_UTENTE)
    salvato = store.leggi_impostazione(conn, sorprese.CHIAVE, "") or ""
    try:
        piano = json.loads(salvato) if salvato else {}
    except ValueError:
        piano = {}
    piano, da_mandare, saltati = sorprese.aggiorna_piano(
        piano, momento, config.PING_PER_SETTIMANA, config.PING_ORA_DA, config.PING_ORA_A,
        config.PING_SOLO_FERIALI, rng)
    nuovo = json.dumps(piano)
    if nuovo != salvato:
        store.scrivi_impostazione(conn, sorprese.CHIAVE, nuovo)
    for orario in saltati:
        print(f"    messaggio a sorpresa delle {orario[11:]} del {orario[:10]} saltato: il bot era spento")
    if not da_mandare:
        return None
    if (store.leggi_impostazione(conn, "pausa", "0") == "1"
            or store.leggi_impostazione(conn, "modalita", "quotidiano") == "silenzioso"):
        print("    messaggio a sorpresa non mandato: bot in pausa o in modalità silenziosa")
        return None
    testo = messaggio_sorpresa(conn, serie)
    esito = telegram_client.invia(config.TELEGRAM_TOKEN, padrone(), testo, timeout=config.TIMEOUT_RETE_SECONDI)
    print(f"  {momento:%H:%M} messaggio a sorpresa ({'mandato' if esito else esito.motivo})")
    return testo


def ascolta(percorso_db=None, serie="coinbase", giri=None, attesa=25):
    """Ciclo di ascolto: resta in attesa dei comandi e risponde. Ctrl-C per fermarlo.

    `giri` limita il numero di cicli (serve ai test); None = per sempre.
    Risponde solo al chat_id configurato: e' un bot personale, non un servizio pubblico.
    """
    config.load_dotenv()
    conn = store.apri(percorso_db)
    offset = int(store.leggi_impostazione(conn, "telegram_offset", 0) or 0)
    print(f"In ascolto. Autorizzati: {', '.join(sorted(autorizzati(conn))) or 'nessuno'}. "
          "Ctrl-C per fermare.")
    # Il menu che Telegram mostra digitando "/" si registra a ogni avvio: cosi' ogni comando nuovo aggiunto a
    # telegram_client.MENU_COMANDI compare da solo, senza ricordarsi di lanciare --menu. Se fallisce non e'
    # grave: l'ascolto parte lo stesso.
    ok_menu, esito_menu = sincronizza_menu(conn)
    print(f"Menu dei comandi: {esito_menu}.")
    print("Messaggi a sorpresa: " + (f"{config.PING_PER_SETTIMANA} a settimana, fra le {config.PING_ORA_DA} "
                                     f"e le {config.PING_ORA_A}" if config.PING_PER_SETTIMANA > 0 else "spenti") + ".")
    fatti, guasti = 0, 0
    while giri is None or fatti < giri:
        fatti += 1
        ok, risultato = telegram_client.eventi(config.TELEGRAM_TOKEN, offset, attesa)
        if not ok:
            # tipicamente: il PC ha perso la rete. Si aspetta sempre di piu' invece di martellare
            # (5s, 10s, 20s... fino a 5 minuti), e si scrive solo il primo errore di una serie.
            guasti += 1
            pausa_rete = min(5 * 2 ** (guasti - 1), 300)
            if guasti == 1 or guasti % 10 == 0:
                print(f"  {datetime.datetime.now():%H:%M:%S} problema con Telegram "
                      f"(tentativo {guasti}): {risultato} — riprovo fra {pausa_rete}s")
            time.sleep(pausa_rete)
            continue
        if guasti:
            print(f"  {datetime.datetime.now():%H:%M:%S} rete tornata dopo {guasti} tentativi")
            guasti = 0
        for evento in risultato:
            offset = evento["update_id"] + 1
            store.scrivi_impostazione(conn, "telegram_offset", offset)
            if evento["tipo"] is None:
                continue
            chat_id = evento.get("chat_id")
            ricorda_nome(conn, evento.get("utente_id"), evento.get("nome"))
            prima = autorizzati(conn)
            ora = f"{datetime.datetime.now():%H:%M:%S}"
            if evento["tipo"] == "pulsante":
                print(f"  {ora} pulsante da {evento.get('utente_id')}: {evento['dati']}")
                esito = gestisci_pulsante(conn, evento["dati"], evento.get("utente_id"))
                telegram_client.rispondi_pulsante(config.TELEGRAM_TOKEN, evento.get("callback_id"),
                                                  esito.get("avviso"))
                if esito.get("testo"):
                    telegram_client.modifica(config.TELEGRAM_TOKEN, chat_id, evento.get("message_id"),
                                             esito["testo"])
            else:
                print(f"  {ora} da {chat_id}: {evento['testo']}")
                try:
                    risposta = gestisci(conn, evento["testo"], serie, chat_id)
                except Exception as exc:                      # un comando non deve uccidere il bot
                    risposta = f"Qualcosa è andato storto con questo comando ({type(exc).__name__})."
                    print(f"    errore: {exc}")
                esito_invio = _manda(chat_id, risposta)
                print(f"    risposto ({'ok' if esito_invio else esito_invio.motivo})")
            dopo = autorizzati(conn)
            if dopo != prima:                                   # accessi cambiati: si rifanno i menu
                ok_menu, esito_menu = sincronizza_menu(conn, rimossi=sorted(prima - dopo))
                print(f"    menu aggiornati: {esito_menu}")
        try:                                                    # a ogni giro: è l'ora di farsi vivo?
            controlla_sorprese(conn, serie)
        except Exception as exc:                                # non deve mai fermare l'ascolto
            print(f"    messaggi a sorpresa: errore {type(exc).__name__}: {exc}")
    conn.close()
    return 0
