"""Entry point del bot (F0.1 del piano).

Comandi:
    python3 bot/main.py --dry-run     stampa la configurazione, non tocca rete ne' database
    python3 bot/main.py --bootstrap   crea il database e lo carica dai CSV in data/ (niente rete)
    python3 bot/main.py --aggiorna    scarica solo i giorni mancanti dalle tre fonti
    python3 bot/main.py --stato       controlli di sanita' + fotografia del giorno (niente rete)
    python3 bot/main.py --giornaliero  aggiorna, controlla e stampa (quello che fara' il timer)

Aggiungendo `--serie coinmetrics` gli indicatori si calcolano sulla serie PriceUSD di
CoinMetrics invece che sulle chiusure Coinbase: serve a riprodurre i numeri di docs/02.

Telegram non e' ancora collegato: e' la fase F4. Qui si vede in console esattamente cio'
che il bot avra' in mano quando parlera'.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from bot import config                                    # noqa: E402
from bot import telegram_client                           # noqa: E402
from bot import comandi                                   # noqa: E402
from botbtc import dataset, engine, messaggi, sanity, store   # noqa: E402


def _stampa_titolo(testo):
    print("\n" + testo)
    print("-" * len(testo))


def comando_dry_run():
    config.load_dotenv()
    _stampa_titolo("Configurazione del bot (nessuna rete, nessun database)")
    for chiave, valore in config.riassunto().items():
        print(f"  {chiave:42} {valore}")
    mancanti = [n for n in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID") if not getattr(config, n)]
    if mancanti:
        print("\n  Nota: " + ", ".join(mancanti) + " non configurati - serviranno alla fase F4 "
              "(copiare bot/.env.example in bot/.env).")
    return 0


def comando_bootstrap(percorso_db=None):
    conn = store.apri(percorso_db)
    caricate = store.bootstrap_da_csv(conn)
    _stampa_titolo("Caricamento iniziale dai CSV di data/ (nessuna rete)")
    for tabella, n in caricate.items():
        print(f"  {tabella:8} {n:6} righe caricate" if n else f"  {tabella:8}      0 righe (tabella gia' popolata)")
    print("\n  righe in archivio:", store.conteggi(conn))
    for tabella in store.TABELLE:
        print(f"    {tabella:8} {store.prima_data(conn, tabella)} -> {store.ultima_data(conn, tabella)}")
    conn.close()
    return 0


def comando_aggiorna(percorso_db=None):
    conn = store.apri(percorso_db)
    if store.conteggi(conn)["prezzi"] == 0:
        print("  archivio vuoto: eseguo prima il caricamento dai CSV")
        store.bootstrap_da_csv(conn)
    rapporto = store.aggiorna_da_rete(conn, timeout=config.TIMEOUT_RETE_SECONDI,
                                      tentativi=config.TENTATIVI_RETE)
    _stampa_titolo("Aggiornamento dalle fonti")
    problemi = 0
    for fonte, voce in rapporto.items():
        stato = f"{voce['nuove']} righe nuove, ultima {voce['ultima']}"
        if voce["fonte"]:
            stato += f", fonte {voce['fonte']}"
        if voce.get("nota"):
            stato += f" [{voce['nota']}]"
        print(f"  {fonte:8} {stato}")
        if voce["errore"]:
            problemi += 1
            print(f"           PROBLEMA: {voce['errore']}")
    conn.close()
    return 0 if problemi == 0 else 1


def comando_stato(percorso_db=None, serie="coinbase"):
    conn = store.apri(percorso_db)
    if store.conteggi(conn)["prezzi"] == 0:
        print("  archivio vuoto: eseguire prima --bootstrap")
        conn.close()
        return 1
    _stampa_titolo("Controlli di sanita'")
    problemi = sanity.rapporto(conn, salto_max=config.SALTO_PREZZO_MAX_GIORNALIERO,
                               eta_prezzo=config.ETA_MASSIMA_PREZZO_GIORNI,
                               eta_mvrv=config.ETA_MASSIMA_MVRV_GIORNI,
                               eta_fng=config.ETA_MASSIMA_FNG_GIORNI)
    print("  " + sanity.stampa(problemi).replace("\n", "\n  "))
    compromesse = sanity.fonti_compromesse(problemi)

    ds = dataset.carica(conn, serie=serie)
    foto = dataset.fotografia(ds)
    _stampa_titolo(f"Fotografia del giorno (serie prezzo: {ds.fonte_prezzo})")
    print("  " + dataset.riga_di_stato(foto))
    print(f"\n  nucleo di soli prezzi completo: {'si' if foto['nucleo_completo'] else 'NO'}")
    if foto["ingredienti_mancanti"]:
        print("  ingredienti mancanti:", ", ".join(foto["ingredienti_mancanti"]))
    if compromesse:
        print("  fonti da dichiarare come non affidabili nel messaggio:", ", ".join(sorted(compromesse)))
    conn.close()
    return 0


def _prepara_stati(conn, serie):
    """Dataset + percentili + serie degli stati: quello che serve per parlare."""
    ds = dataset.carica(conn, serie=serie)
    dataset.aggiungi_percentili(ds, config.FINESTRA_PERCENTILE_GIORNI)
    percentili = [dataset.percentili_del_giorno(ds, i) for i in range(len(ds))]
    valori = [{k: ds.ind.get(k, [None] * len(ds))[i] for k in engine.PESI} for i in range(len(ds))]
    righe = engine.serie_stati(percentili, config.parametri_motore(), valori)
    return ds, righe


def comando_messaggio(percorso_db=None, serie="coinbase", giorno=None, formato="tutti"):
    conn = store.apri(percorso_db)
    if store.conteggi(conn)["prezzi"] == 0:
        print("  archivio vuoto: eseguire prima --bootstrap")
        conn.close()
        return 1
    ds, righe = _prepara_stati(conn, serie)
    indice = ds.indice(giorno) if giorno else len(ds) - 1
    foto = dataset.fotografia(ds, ds.dates[indice])
    parametri = config.parametri_motore()

    # stato precedente DIVERSO da quello di oggi: serve solo al messaggio di cambio stato
    precedente = engine.NORMALE
    stato_oggi = righe[indice].get("stato_confermato")
    for j in range(indice - 1, max(0, indice - 400), -1):
        passato = righe[j].get("stato_confermato")
        if passato and passato != stato_oggi:
            precedente = passato
            break

    da_stampare = []
    if formato in ("polso", "tutti"):
        da_stampare.append(("POLSO", messaggi.polso(ds, righe, indice, foto, parametri,
                                                    config.BUDGET_MENSILE_EUR)))
    if formato in ("cambio", "tutti"):
        da_stampare.append(("CAMBIO DI STATO", messaggi.cambio_stato(
            ds, righe, indice, foto, parametri, precedente, config.BUDGET_MENSILE_EUR,
            config.TETTO_STRAORDINARIO_MESI)))
    if formato in ("analisi", "tutti"):
        da_stampare.append(("ANALISI COMPLETA", messaggi.analisi_completa(
            ds, righe, indice, foto, parametri, config.BUDGET_MENSILE_EUR,
            config.TETTO_STRAORDINARIO_MESI)))
    for titolo, testo in da_stampare:
        _stampa_titolo(f"{titolo} — {ds.dates[indice]} (serie {ds.fonte_prezzo})")
        print(testo)
        print(f"\n[{len(testo.splitlines())} righe, {len(testo)} caratteri]")
    conn.close()
    return 0


def comando_telegram_chat():
    """Trova il chat_id: serve che qualcuno abbia scritto al bot almeno una volta."""
    config.load_dotenv()
    _stampa_titolo("Telegram — verifica del token e ricerca del chat_id")
    ok, descrizione = telegram_client.chi_sono(config.TELEGRAM_TOKEN)
    print(f"  token: {'valido' if ok else 'PROBLEMA'} — {descrizione}")
    if not ok:
        return 1
    ok, chat = telegram_client.chat_disponibili(config.TELEGRAM_TOKEN)
    if not ok:
        print(f"  PROBLEMA: {chat}")
        return 1
    if not chat:
        print("  nessuna chat: apri Telegram, scrivi /start al bot e rilancia questo comando.")
        return 1
    for chat_id, nome, tipo in chat:
        print(f"  chat_id {chat_id}  ({nome}, {tipo})")
    print("\n  Metti il chat_id in bot/.env come BOTBTC_TELEGRAM_CHAT_ID.")
    return 0


def comando_invia(percorso_db=None, serie="coinbase", giorno=None, formato="polso", prova=False):
    """Manda davvero il messaggio su Telegram (F4.1)."""
    config.load_dotenv()
    if prova:
        testo = telegram_client.BENVENUTO
    else:
        conn = store.apri(percorso_db)
        if store.conteggi(conn)["prezzi"] == 0:
            print("  archivio vuoto: eseguire prima --bootstrap")
            conn.close()
            return 1
        ds, righe = _prepara_stati(conn, serie)
        indice = ds.indice(giorno) if giorno else len(ds) - 1
        foto = dataset.fotografia(ds, ds.dates[indice])
        parametri = config.parametri_motore()
        if formato == "analisi":
            testo = messaggi.analisi_completa(ds, righe, indice, foto, parametri,
                                              config.BUDGET_MENSILE_EUR,
                                              config.TETTO_STRAORDINARIO_MESI)
        else:
            testo = messaggi.polso(ds, righe, indice, foto, parametri, config.BUDGET_MENSILE_EUR)
        conn.close()

    _stampa_titolo("Invio su Telegram")
    print(testo)
    esito = telegram_client.invia(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID, testo,
                                  timeout=config.TIMEOUT_RETE_SECONDI)
    if esito:
        print(f"\n  inviato (message_id {esito.message_id}).")
        return 0
    print(f"\n  NON inviato: {esito.motivo}")
    return 1


def comando_report(percorso_db=None, serie="coinbase", invia=True):
    """Il giro quotidiano completo: aggiorna, controlla, decide, manda, registra.

    E' quello che fara' il timer sul VPS. Ordine pensato perche' un guasto non produca silenzio:
    se una fonte manca il bot parla lo stesso col nucleo di prezzo (F2.6) e lo dichiara; se il
    nucleo stesso non c'e', manda un messaggio di allarme invece di tacere (F4.3).
    """
    config.load_dotenv()
    conn = store.apri(percorso_db)
    if store.conteggi(conn)["prezzi"] == 0:
        store.bootstrap_da_csv(conn)

    rapporto = store.aggiorna_da_rete(conn, timeout=config.TIMEOUT_RETE_SECONDI,
                                      tentativi=config.TENTATIVI_RETE)
    problemi = sanity.rapporto(conn, salto_max=config.SALTO_PREZZO_MAX_GIORNALIERO,
                               eta_prezzo=config.ETA_MASSIMA_PREZZO_GIORNI,
                               eta_mvrv=config.ETA_MASSIMA_MVRV_GIORNI,
                               eta_fng=config.ETA_MASSIMA_FNG_GIORNI)
    compromesse = sanity.fonti_compromesse(problemi)

    ds, righe = _prepara_stati(conn, serie)
    indice = len(ds) - 1
    foto = dataset.fotografia(ds, ds.dates[indice])
    parametri = config.parametri_motore()
    valutazione = righe[indice]
    stato = valutazione.get("stato_confermato", valutazione["stato"])

    giorno_precedente, stato_precedente = store.ultimo_stato_registrato(conn)
    cambiato = stato_precedente is not None and stato_precedente != stato

    if stato == engine.SCONOSCIUTO or "prezzi" in compromesse:
        testo = ("AphroditeBTC — non sono riuscito a leggere il mercato.\n"
                 f"Problemi: {'; '.join(p.messaggio for p in sanity.gravi(problemi)) or 'dati insufficienti'}.\n"
                 "Non invento un numero: appena le fonti tornano riprendo.")
    elif cambiato:
        testo = messaggi.cambio_stato(ds, righe, indice, foto, parametri, stato_precedente,
                                      config.BUDGET_MENSILE_EUR, config.TETTO_STRAORDINARIO_MESI)
    else:
        testo = messaggi.polso(ds, righe, indice, foto, parametri, config.BUDGET_MENSILE_EUR)

    if compromesse and stato != engine.SCONOSCIUTO:
        testo += "\nAttenzione: " + ", ".join(sorted(compromesse)) + " non affidabili oggi."

    pausa = store.leggi_impostazione(conn, "pausa", "0") == "1"
    modalita = store.leggi_impostazione(conn, "modalita", "quotidiano")
    if pausa:
        invia = False
        print("  (in pausa: registro ma non mando)")
    elif modalita == "silenzioso" and not cambiato and stato != engine.SCONOSCIUTO:
        invia = False
        print("  (modalità silenziosa: niente da dire oggi, lo stato non è cambiato)")

    esito = None
    inviato = False
    if invia:
        risultato = telegram_client.invia(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID, testo,
                                          timeout=config.TIMEOUT_RETE_SECONDI)
        inviato, esito = bool(risultato), (None if risultato else risultato.motivo)

    indicatori = {chiave: ds.ind.get(chiave, [None] * len(ds))[indice] for chiave in engine.PESI}
    indicatori.update({f"pct_{k}": (ds.ind.get(f"pct_{k}") or [None] * len(ds))[indice]
                       for k in engine.PESI})
    store.scrivi_registro(conn, ds.dates[indice], stato,
                          {"economico": valutazione["punteggio_economico"],
                           "caro": valutazione["punteggio_caro"],
                           "moltiplicatore": valutazione.get("moltiplicatore")},
                          foto["prezzo"], indicatori, testo, inviato, esito)

    _stampa_titolo(f"Report del {ds.dates[indice]}")
    for fonte, voce in rapporto.items():
        print(f"  {fonte:8} {voce['nuove']} nuove, ultima {voce['ultima']}"
              + (f" — PROBLEMA: {voce['errore']}" if voce["errore"] else ""))
    if problemi:
        print("  controlli: " + "; ".join(f"{p.gravita}/{p.fonte}" for p in problemi))
    print(f"  stato: {stato}" + (f" (era {stato_precedente}: CAMBIATO)" if cambiato else ""))
    print("\n" + testo)
    print(f"\n  {'inviato su Telegram' if inviato else 'NON inviato: ' + str(esito) if invia else 'invio disattivato'}"
          f" · registrato in archivio")
    conn.close()
    return 0 if (not invia or inviato) else 1


def comando_registro(percorso_db=None, quante=10):
    conn = store.apri(percorso_db)
    _stampa_titolo(f"Ultime {quante} righe del registro (la memoria per l'autopsia a 12 mesi)")
    righe = store.righe_registro(conn, quante)
    if not righe:
        print("  vuoto: il registro si riempie a ogni --report")
    for r in righe:
        punteggio = "n/d" if r["punteggio_economico"] is None else f"{r['punteggio_economico']:.2f}"
        print(f"  {r['data']}  {r['stato']:14} punteggio {punteggio:>5}  "
              f"prezzo {r['prezzo']:>10,.0f}  {'inviato' if r['inviato'] else 'non inviato'}")
    conn.close()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Bot BTC — report e sforzo (fasi F0-F1)")
    gruppo = p.add_mutually_exclusive_group(required=True)
    gruppo.add_argument("--dry-run", action="store_true", help="stampa la configurazione e basta")
    gruppo.add_argument("--bootstrap", action="store_true", help="crea il database dai CSV in data/")
    gruppo.add_argument("--aggiorna", action="store_true", help="scarica i giorni mancanti")
    gruppo.add_argument("--stato", action="store_true", help="sanita' + fotografia del giorno")
    gruppo.add_argument("--giornaliero", action="store_true", help="aggiorna, controlla e stampa")
    gruppo.add_argument("--messaggio", action="store_true",
                        help="genera i messaggi (polso / cambio stato / analisi) per un giorno")
    gruppo.add_argument("--telegram-chat", action="store_true",
                        help="verifica il token e mostra i chat_id disponibili")
    gruppo.add_argument("--invia", action="store_true",
                        help="manda il messaggio del giorno su Telegram")
    gruppo.add_argument("--telegram-prova", action="store_true",
                        help="manda il messaggio di benvenuto, per provare il collegamento")
    gruppo.add_argument("--report", action="store_true",
                        help="giro quotidiano completo: aggiorna, decide, manda e registra")
    gruppo.add_argument("--registro", action="store_true",
                        help="mostra le ultime righe registrate")
    gruppo.add_argument("--menu", action="store_true",
                        help="registra su Telegram il menu dei comandi (quello che appare con \"/\")")
    gruppo.add_argument("--ascolta", action="store_true",
                        help="resta in ascolto e risponde ai comandi Telegram")
    gruppo.add_argument("--guida", action="store_true",
                        help="manda su Telegram la guida: come si legge il report")
    p.add_argument("--db", default=None, help="percorso del database (default: data/botbtc.sqlite3)")
    p.add_argument("--serie", default=None, choices=("coinbase", "coinmetrics"),
                   help="serie di prezzo per gli indicatori (default: da config)")
    p.add_argument("--data", default=None, help="giorno da raccontare, AAAA-MM-GG (default: l'ultimo)")
    p.add_argument("--formato", default="tutti", choices=("polso", "cambio", "analisi", "tutti"))
    p.add_argument("--giri", type=int, default=None,
                   help="con --ascolta: quanti cicli di attesa fare prima di uscire (per le prove)")
    args = p.parse_args(argv)
    serie = args.serie or config.SERIE_PREZZO_LIVE

    if args.dry_run:
        return comando_dry_run()
    if args.bootstrap:
        return comando_bootstrap(args.db)
    if args.aggiorna:
        return comando_aggiorna(args.db)
    if args.stato:
        return comando_stato(args.db, serie)
    if args.messaggio:
        import datetime as _dt
        giorno = _dt.date.fromisoformat(args.data) if args.data else None
        return comando_messaggio(args.db, serie, giorno, args.formato)
    if args.menu:
        config.load_dotenv()
        ok, messaggio = telegram_client.registra_menu(config.TELEGRAM_TOKEN)
        print(f"  menu comandi: {'registrato — ' if ok else 'PROBLEMA — '}{messaggio}")
        for nome, descrizione in telegram_client.MENU_COMANDI:
            print(f"    /{nome:12} {descrizione}")
        return 0 if ok else 1
    if args.ascolta:
        return comandi.ascolta(args.db, serie, giri=args.giri)
    if args.guida:
        config.load_dotenv()
        esito = telegram_client.invia(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID,
                                      messaggi.guida(), timeout=config.TIMEOUT_RETE_SECONDI)
        print(messaggi.guida())
        print(f"\n  {'inviata' if esito else 'NON inviata: ' + str(esito.motivo)}")
        return 0 if esito else 1
    if args.report:
        return comando_report(args.db, serie, invia=True)
    if args.registro:
        return comando_registro(args.db)
    if args.telegram_chat:
        return comando_telegram_chat()
    if args.telegram_prova:
        return comando_invia(args.db, serie, None, args.formato, prova=True)
    if args.invia:
        import datetime as _dt2
        giorno = _dt2.date.fromisoformat(args.data) if args.data else None
        return comando_invia(args.db, serie, giorno, args.formato)
    if args.giornaliero:
        esito = comando_aggiorna(args.db)
        return comando_stato(args.db, serie) or esito
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
