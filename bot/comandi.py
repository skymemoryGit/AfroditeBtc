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
import time

from bot import config, telegram_client
from botbtc import dataset, engine, messaggi, sanity, store

AIUTO = ("Comandi:\n"
         "/analisi — il report completo di oggi\n"
         "/stato — due righe, al volo\n"
         "/perche — perché oggi siamo in questo stato\n"
         "/guida — come si legge il report\n"
         "/silenzioso — scrivimi solo quando cambia lo stato\n"
         "/quotidiano — torna al battito di ogni giorno\n"
         "/pausa e /riprendi — sospendi o riattiva tutto\n"
         "/registro — le ultime giornate\n"
         "/id — il tuo identificativo Telegram")

AIUTO_PADRONE = ("\n\n<b>Solo per te</b>\n"
                 "/utenti — chi può usare il bot\n"
                 "/autorizza &lt;id&gt; — dai accesso a qualcuno\n"
                 "/revoca &lt;id&gt; — toglilo")


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

    # --- comandi che valgono per chiunque
    if comando == "/id":
        return (f"Il tuo identificativo Telegram è <code>{chi}</code>.\n"
                + ("Sei autorizzato a usare il bot." if ammesso else
                   "Non sei ancora autorizzato: manda questo numero al proprietario del bot."))
    if not ammesso:
        return ("Questo è un bot personale e non sei fra le persone autorizzate.\n"
                f"Il tuo identificativo è <code>{chi}</code>: mandalo al proprietario se vuoi accesso.")

    # --- gestione degli accessi, solo per il padrone
    if comando in ("/utenti", "/autorizza", "/revoca"):
        if not e_padrone:
            return "Solo il proprietario del bot può gestire gli accessi."
        if comando == "/utenti":
            righe = ["👥 <b>Chi può usare il bot</b>"]
            for uno in sorted(autorizzati(conn)):
                righe.append(f"▸ <code>{uno}</code>" + (" <i>(tu, proprietario)</i>" if uno == padrone() else ""))
            righe.append("\n<i>Per aggiungere: /autorizza &lt;id&gt; — l'altra persona trova il suo "
                         "con /id</i>")
            return "\n".join(righe)
        if not argomento.lstrip("-").isdigit():
            return f"Serve un identificativo numerico: <code>{comando} 123456789</code>"
        if comando == "/autorizza":
            autorizza(conn, argomento)
            return (f"✅ <code>{argomento}</code> ora può usare il bot.\n"
                    "<i>Riceverà le risposte ai comandi, non il report quotidiano: quello resta tuo.</i>")
        esito = revoca(conn, argomento)
        if esito is None:
            return "Non posso togliere te stesso: sei il proprietario."
        return f"🚫 <code>{argomento}</code> non può più usare il bot."

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
    fatti, guasti = 0, 0
    while giri is None or fatti < giri:
        fatti += 1
        ok, risultato = telegram_client.aggiornamenti(config.TELEGRAM_TOKEN, offset, attesa)
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
        for update_id, chat_id, testo in risultato:
            offset = update_id + 1
            store.scrivi_impostazione(conn, "telegram_offset", offset)
            if not testo:
                continue
            print(f"  {datetime.datetime.now():%H:%M:%S} da {chat_id}: {testo}")
            try:
                risposta = gestisci(conn, testo, serie, chat_id)
            except Exception as exc:                      # un comando non deve uccidere il bot
                risposta = f"Qualcosa è andato storto con questo comando ({type(exc).__name__})."
                print(f"    errore: {exc}")
            esito = telegram_client.invia(config.TELEGRAM_TOKEN, chat_id, risposta,
                                          timeout=config.TIMEOUT_RETE_SECONDI)
            print(f"    risposto ({'ok' if esito else esito.motivo})")
    conn.close()
    return 0
