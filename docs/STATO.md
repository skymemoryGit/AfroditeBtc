# STATO DEL PROGETTO — Bot BTC

Aggiornato: **2026-09-23, sessione 13**. Questo è il foglio da guardare per primo: dice a che punto siamo.
Il dettaglio di *cosa* va fatto in ogni fase è in [`03_piano_sviluppo.md`](03_piano_sviluppo.md).

## In una riga

**Il bot vive**: @AphroBtcbot manda il report su Telegram, con i dati aggiornati dalle tre fonti e tutto
registrato in archivio. Gira ancora a mano dal PC: manca il deploy sul VPS (F5) perché parta da solo ogni giorno.

## Le fasi

| fase | cosa | stato | dove sta |
|---|---|---|---|
| **F0** | fondamenta: cartella `bot/`, configurazione, entry point | ✅ **FATTA** (sess. 06) | `bot/config.py`, `bot/main.py` |
| **F1** | strato dati: fetcher con fallback, archivio SQLite, controlli di sanità | ✅ **FATTA** (sess. 06) | `botbtc/fetchers.py`, `store.py`, `sanity.py`, `dataset.py` |
| **F2** | motore dei tre stati + test di accettazione storico | ✅ **FATTA** (sess. 07) | `botbtc/engine.py`, `docs/04_regola_stati.md` |
| **F3** | il testo dei messaggi: polso, cambio stato, analisi completa | ✅ **FATTA** (sess. 09) | `botbtc/messaggi.py`, `docs/05_messaggi.md` |
| **F4** | Telegram: invio, comandi, gestione errori | ✅ **FATTA** (sess. 12) — invio, 10 comandi, menu, autorizzazioni | `bot/telegram_client.py`, `bot/comandi.py` |
| **F5** | messa in esercizio sul VPS Contabo (systemd, log, backup) | ⬜ **DA FARE — si riparte da qui** | — |
| **F6** | esercizio, paper-trading del segnale di uscita, autopsia a 3/6/12 mesi | 🟡 il registro giornaliero (F6.1) è già attivo | tabella `registro` |
| **F7** | presentazione per il cliente: slide per chi non ha contesto | 🟡 appunti iniziati | `docs/06_appunti_presentazione.md` |

**Esperimento aperto**: far entrare Google Trends nel punteggio del motore (oggi è solo contesto nel
messaggio, D34) — richiede ricalibrazione e nuovo test di accettazione F2.3 con otto ingredienti.

**Dove si riparte**: F5 — mettere il bot sul VPS Contabo con un systemd timer, così il report arriva ogni
mattina senza che il PC sia acceso. Poi F4.2, i comandi (`/analisi`, `/stato`, `/perche`, `/pausa`).

**Obiettivo dichiarato**: primo messaggio reale su Telegram entro due settimane. ✅ **Raggiunto il 2026-09-22**,
tre giorni dopo la stesura del piano.

## Cosa funziona già, oggi

- **(sessione 13, D42)** I confronti coi 4 anni si leggono con i giorni veri: *"negli ultimi 4 anni è stato più
  alto di oggi in 386 giorni su 1.460 (26%)"*, sempre nello stesso verso. **Dopo ogni modifica al codice
  il processo di ascolto va riavviato** (chiudere e riaprire `bot/avvia_ascolto.bat`): Python legge il codice
  solo all'avvio. Il report quotidiano no, parte da zero ogni volta.

- `python3 bot/main.py --giornaliero` scarica i giorni mancanti dalle tre fonti, controlla i dati e stampa la
  fotografia del giorno. Provato davvero sul PC il 2026-09-20.
- Il motore dice in che stato è il mercato (*straordinario / normale / freno*), con quali ingredienti ha deciso e
  quanto sforzo varrebbe (moltiplicatore).
- I tre messaggi si generano per qualunque giorno: `python3 bot/main.py --messaggio [--data 2026-06-29]`.
- **Comandi**: `/analisi` `/stato` `/perche` `/guida` `/silenzioso` `/quotidiano` `/registro` `/pausa`
  `/riprendi` `/id`, più `/utenti` `/autorizza` `/revoca` per il solo proprietario. Il menu si registra con
  `python3 bot/main.py --menu`; l'ascolto si avvia con `bot/avvia_ascolto.bat`.
- **La guida da fissare in chat**: `python3 bot/main.py --guida` — cosa vuol dire ogni riga del report.
- **Il giro quotidiano vero**: `python3 bot/main.py --report` — aggiorna, controlla, decide, manda su Telegram
  e scrive la riga nel registro. `--registro` mostra le ultime righe.
- **56 test automatici**, tutti verdi (`python3 -m unittest discover -s tests`).

## Cosa NON esiste ancora

- **Il bot risponde ai comandi solo mentre `bot/avvia_ascolto.bat` è aperto sul PC**: per averli sempre serve
  il servizio sul VPS (F5). Il report quotidiano invece non dipende dall'ascolto.
- Nessun collegamento a Telegram, nessun token configurato.
- Niente gira sul VPS: il report parte a mano dal PC.
- (fatto) Il registro giornaliero è attivo dal 21/09/2026.

## In attesa di una tua decisione

| cosa | perché serve | quando serve |
|---|---|---|
| **Tetto dello sforzo straordinario per ciclo**, in mesi equivalenti di budget (es. 12 = 12 × 200 €) | è l'unico parametro che dipende da quanto puoi permetterti, non dai dati. La simulazione dice che a 12 non è mai stato un vincolo (il ciclo 2022-23 ne ha usati 6,9), a 6 inizia a mordere | prima di F3: il messaggio deve poter dire "usati X di Y" |
| Exchange e fee reali (Binance/Kraken ~0,1 % o app tipo Revolut ~1,5 %) | non blocca il bot di report | più avanti, col v6 |
| Valuta degli ordini (EUR probabile) | non blocca | più avanti |

## I documenti, in ordine di lettura

1. [`CLAUDE.md`](../CLAUDE.md) — regole del progetto, per chi ci lavora
2. **questo foglio** — a che punto siamo
3. [`03_piano_sviluppo.md`](03_piano_sviluppo.md) — il piano a fasi con le verifiche
4. [`00_decisioni.md`](00_decisioni.md) — le 30 decisioni prese finora, con la ragione di ognuna
5. [`04_regola_stati.md`](04_regola_stati.md) — la regola dei tre stati: parametri, test, limiti
6. [`02_indicatori_bot_report.md`](02_indicatori_bot_report.md) — gli indicatori, con numeri e limiti
7. [`01_analisi_pseudocodice_v5.1.md`](01_analisi_pseudocodice_v5.1.md) — l'analisi della vecchia spec BUY+SELL
8. [`tracking/`](tracking) — una nota per sessione, dalla 01 alla 07

## Numeri da ricordare

- Stato straordinario: **12,0 %** dei giorni dal 2011. Rendimento mediano a 12 mesi **+78 %**, 87 % positivi.
  Ma nell'ultimo ciclo la mediana è **+40 %**: i cicli si stanno accorciando (D30).
- Stato freno: **4,4 %** dei giorni, il 79 % entro 12 mesi da un massimo, mediana a 12 mesi **−18 %**.
- Simulazione 2015-2026: **+12,3 % di BTC** rispetto al solo ricorrente, avendo versato il 10,3 % in più.
  A parità di depositi il tempismo vale **+1,8 %**: il bot serve a farti versare di più, non a indovinare il minimo.
- Giugno 2026 (il caso che ha fatto nascere il progetto): acceso dal 6 all'11 e dal 25 al 30 giugno.
