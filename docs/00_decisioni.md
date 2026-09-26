# Decisioni del progetto AphroditeBTC

Le decisioni prese finora, raccolte in un posto solo: le note di sessione raccontano *cosa è successo*,
questo file dice *cosa vale adesso*. Chi arriva nuovo legge questo e non deve ricostruire nulla dalle note.

Stato: **decisa** = si applica · **proposta** = suggerita, non ancora confermata dall'utente · **aperta** = da decidere.
Ogni sessione che decide qualcosa aggiunge una riga qui.

---

## Metodo e vincoli di fondo

**D1 — Metrica di valutazione: BTC accumulati rispetto al DCA puro, a parità di depositi.** *(2026-09-19, decisa)*
Il ROI in euro non distingue le strategie: con 200 €/mese e BTC che fa ±30 % al mese, il risultato del mese lo
decide il prezzo, non il bot. L'unica cosa che il bot può migliorare è il prezzo medio di carico.
*Fonte: `01_analisi_pseudocodice_v5.1.md` §6.*

**D2 — Solo API pubbliche documentate, niente scraping.** *(2026-09-19, decisa)*
L'idea iniziale di raschiare TradingView è stata scartata: fragile, contro i loro termini, e inutile — tutto ciò che
il bot deve vedere si calcola da una serie di chiusure giornaliere più due API gratuite. *Fonte: analisi §5.*

**D3 — Umano nel loop: il bot notifica, l'utente esegue.** *(2026-09-19, decisa)*
Nessun ordine automatico, nessuna leva, nessuna chiave di exchange con permessi di trading. *Fonte: spec v5.1, analisi §1.*

## Scope

**D4 — Prima il bot di monitoraggio e report, poi l'esecuzione.** *(2026-09-20, sessione 02, decisa)*
L'analisi ha mostrato che il timing automatico sul lato BUY vale circa quanto il DCA puro e che il modulo SELL
com'è scritto perde valore: costruire subito il bot BUY+SELL significherebbe automatizzare qualcosa di non dimostrato.
Il valore immediato e sicuro è avere occhi sul mercato ogni giorno. Il piano v6 non è abbandonato, è rinviato.

**D5 — Nel bot di report non c'è nessun modulo SELL.** *(2026-09-20, sessione 02, decisa)*

**D6 — Set di indicatori esteso rispetto a quello minimo dell'analisi.** *(2026-09-20, sessione 02, decisa)*
Al set iniziale (media200/Mayer, drawdown dal massimo 365 giorni, RSI-14 giornaliero, Fear & Greed) si aggiungono
RSI-14 settimanale, 200-WMA, Pi Cycle Top e MVRV. I primi tre costano zero (stessa serie di prezzi già scaricata).

**D7 — Il report include un confronto storico automatico.** *(2026-09-20, sessione 02, decisa)*
"L'ultima volta che eri in questa situazione era il …, e dopo 6/12 mesi BTC ha fatto …". Non è un indicatore nuovo:
è raccontare meglio i dati già presenti in `data/`. È il pezzo che sarebbe servito a giugno 2026.

## Indicatori (sessione 03, con i numeri in `02_indicatori_bot_report.md`)

**D8 — MVRV: si usano il valore grezzo e il percentile a 4 anni. Lo Z-score classico non è una soglia.** *(2026-09-20, decisa)*
Ai massimi di ciclo lo Z-score espansivo crolla di ciclo in ciclo (10,7 → 9,4 → 5,4 → 3,5 → 2,5) perché il denominatore
cresce: le soglie da manuale ("Z > 7 = vendere") sono tarate su un mondo che non c'è più. Il percentile a 4 anni è la
variante più stabile fra i cicli (coefficiente di variazione 0,069 contro 0,502 dello Z). Lo Z resta calcolato come riga
di contesto, quindi la scelta è reversibile senza rifare nulla. *Fonte: `02` §2.*

**D9 — MVRV resta nel set: non è un doppione del Mayer multiple.** *(2026-09-20, decisa)*
Correlati (r = 0,85) ma non equivalenti: a parità di banda di Mayer, i giorni con MVRV sotto la mediana hanno reso
molto di più a 12 mesi. Nel report vanno mostrati separati, mai fusi in un punteggio unico che nasconde il disaccordo.
*Fonte: `02` §3.*

**D10 — Pi Cycle Top declassato a riga informativa.** *(2026-09-20, decisa)*
Quando ha sparato è stato puntualissimo (4 incroci, tutti entro un giorno dal massimo), ma sugli ultimi due massimi
(2021-11 e 2025-10) è rimasto muto e nel ciclo attuale non si è mai avvicinato. Si mostra "quanto manca al segnale",
non si usa come allarme. *Fonte: `02` §4.*

**D11 — `botbtc/indicators.py` è la libreria del bot, non codice usa-e-getta.** *(2026-09-20, decisa)*
Solo libreria standard, nessuna dipendenza esterna, nessun lookahead: ogni valore al giorno *t* deve essere calcolabile
in tempo reale. pandas/numpy sono stati usati solo come secondo parere per verificare i calcoli e non entrano nel progetto.

**D12 — Due serie di prezzi, mai mescolate.** *(2026-09-20, decisa)*
`PriceUSD` di CoinMetrics per gli indicatori lunghi (storia dal 2010), chiusure Coinbase per il backtest v5.1 (dal 2017).
Scarto medio 0,18 %: sono cose diverse (prezzo di riferimento multi-exchange contro chiusura di un exchange).

## Infrastruttura (sessione 04)

**D13 — Il bot girerà sul VPS Contabo (Linux) dell'utente.** *(2026-09-20, decisa)*
Il report deve arrivare ogni giorno: un Raspberry in casa prima o poi si scollega. Il Raspberry resta come fallback.

**D14 — Struttura del progetto: libreria condivisa separata dalla ricerca.** *(2026-09-20, decisa)*
`botbtc/` per il codice che deve essere identico tra backtest e bot live, `data/` alla radice, `backtest/` solo per gli
script di ricerca, `bot/` (da creare) per l'entry point Telegram. Coerente con l'architettura "un solo motore puro"
dell'analisi §8.4: mai due logiche parallele che divergono.

## Charter del bot di report (sessione 05, approvato punto per punto)

**D15 - Tre stati di sforzo invece di due.** *(2026-09-20, decisa)*
*straordinario* (zona rara ed economica: versamento extra, in piu' colpi) - *normale* (i 200 EUR/mese e basta) -
*freno* (zona storicamente cara: nessun versamento straordinario). Il terzo stato e' il gemello speculare del problema
di giugno 2026 e protegge dall'errore piu' costoso di chi compra a rate: mettere una somma grossa sul massimo.

**D16 - In stato di freno il bot non dice mai "vendi".** *(2026-09-20, decisa)*
Dice solo di non aggiungere. L'utente resta libero di alleggerire di sua iniziativa guardando la stessa analisi, ma e'
una sua decisione: il bot non ne e' ne' l'autore ne' il custode. Motivo nei numeri: le soglie del lato "caro" si
sgonfiano a ogni ciclo (MVRV ai massimi 4,43 -> 2,29; RSI settimanale 90 -> 65), mentre quelle del lato "economico"
sono stabili. Una regola di acquisto invecchia bene, una di vendita invecchia male.

**D17 - Paper-trading del segnale di alleggerimento dal primo giorno.** *(2026-09-20, decisa)*
Il bot registra in silenzio cosa avrebbe detto una regola di uscita, senza mandare niente e senza eseguire niente.
Fra dodici mesi si decide con dati veri invece che con opinioni. Costo: una riga di database al giorno.

**D18 - Fiscalita' e commissioni di exchange fuori perimetro nella v1.** *(2026-09-20, decisa)*
Il bot non esegue ordini e non suggerisce vendite: non c'e' nulla su cui possano incidere. Tornano a contare solo se un
giorno si valuta il modulo di alleggerimento (vedi D17) o il v6.

**D19 - Tre modi di parlare.** *(2026-09-20, decisa)*
A) analisi completa su richiesta, in qualsiasi momento; B) polso regolare di due righe, silenzioso, nella maggior parte
dei giorni; C) messaggio d'eccezione quando lo stato cambia. Solo il terzo chiede davvero attenzione.

**D20 - Criterio di successo dichiarato in anticipo.** *(2026-09-20, decisa)*
Fra dodici mesi: il bot ha segnalato le fasi che col senno di poi erano buone, e l'utente ha fatto almeno un acquisto
straordinario grazie a lui. Se no, si spegne o si cambia.

## Implementazione (sessione 06, fasi F0-F1)

**D21 — Telegram con la libreria `python-telegram-bot`, ma solo nel livello `bot/`.** *(2026-09-20, decisa)*
Scelta dell'utente (F0.2), per coerenza con i suoi altri bot. La regola "solo libreria standard" resta valida dove
conta: `botbtc/` (indicatori, fetcher, cache, sanita', motore) non ha e non avra' dipendenze esterne, cosi' backtest e
test girano ovunque con il solo Python. La dipendenza vive in `bot/requirements.txt` e sul VPS in un venv.

**D22 — Il bot live calcola gli indicatori sulle chiusure Coinbase.** *(2026-09-20, decisa)*
Motivo: sono disponibili subito (candela chiusa di ieri), mentre `PriceUSD` di CoinMetrics arriva con un giorno di
ritardo insieme all'MVRV. La storia Coinbase dal 2017 basta per tutti gli indicatori del bot (la 200-WMA richiede
200 settimane, disponibili dal 2020). `PriceUSD` resta la serie della storia lunga (dal 2010) usata in `docs/02` e
nei test storici che devono arrivare prima del 2017. Coerente con D12: dentro un singolo calcolo, mai le due insieme.
Controllo fatto il 2026-09-20 sul dato reale del 19-09: Mayer 1,15 · drawdown −34,9 % · RSI-W 58,8 · P/200-WMA 1,24
calcolati sulle due serie danno gli stessi numeri (RSI giornaliero 64,2 contro 64,3).

**D23 — La cache e l'archivio del bot sono un unico database SQLite.** *(2026-09-20, decisa)*
Si inizializza dai CSV gia' validati in `data/` (nessun riscaricamento della storia) e poi aggiunge un giorno alla
volta, con la fonte segnata riga per riga. Percorso predefinito `data/botbtc.sqlite3`, spostabile con `BOTBTC_DB`
(sul VPS la cartella dati sta fuori dal codice). E' anche la base del logging quotidiano previsto da P1 e F6.1.

**D24 — Quando l'archivio ha gia' il dato piu' recente possibile, la rete non si chiama.** *(2026-09-20, decisa)*
La candela di oggi e' aperta e l'MVRV del giorno T arriva il giorno T+1: il dato piu' fresco che puo' esistere e'
quello di ieri. Senza questa regola la seconda esecuzione della giornata scaricava zero righe e sembrava un guasto.
Il rapporto di aggiornamento distingue ora tre casi: righe nuove, "gia' aggiornato" (con il perche'), errore.

## Il motore dei tre stati (sessione 07, fase F2)

**D25 — La regola combina gli ingredienti con un punteggio di profondità, non con AND né con OR.** *(2026-09-20, decisa)*
Ogni ingrediente viene convertito nel suo percentile su 4 anni e contribuisce in proporzione a quanto è estremo,
con i pesi di `docs/04` §1.3. Numeri del confronto (`docs/04` §4): AND stretto 9,2 % dei giorni e +51 % a 12 mesi;
AND morbido 14,8 % e +58 %; OR largo 58,7 % e +82 % ma con la stessa quota di casi positivi di un giorno qualsiasi;
punteggio 12,0 % dei giorni, +78 % e **87 % di casi positivi**. Il punteggio è l'unico che tiene insieme rarità e qualità.

**D26 — Le soglie si calibrano solo sulla quota di giorni, mai sulle date.** *(2026-09-20, decisa)*
Straordinario ≥ 0,4229 (12,0 % dei giorni), freno ≥ 0,2314. I parametri sono stati scritti in `docs/04` §1 **prima**
di lanciare il test storico; le ri-tarature successive sono contate in `docs/04` §6 (due, entrambe strutturali:
requisito di durata per il freno, moltiplicatore minimo).

**D27 — Il freno si accende solo dopo 60 giorni consecutivi di mercato caro ("freno tardivo").** *(2026-09-20, decisa)*
Scoperta che rende obbligatoria la scelta: a fine dicembre 2020 — inizio del rialzo verso i 60 mila — il mercato era
**più caro di quanto fosse ai massimi del 2021 e del 2025** (MVRV 3,14 contro 2,85 e 2,29; Mayer 2,17 contro 1,48 e
1,18). Nessuna soglia sul livello può accendersi a quei massimi e restare spenta lì: i criteri (e) ed (f) del piano
erano incompatibili. Col requisito di durata il freno resta acceso il 4,4 % dei giorni, il 79 % dei quali entro 12 mesi
da un massimo, e i 12 mesi successivi hanno mediana **−18 %**. Prezzo pagato: coglie 2 massimi su 4. Criteri (e) ed (f)
riscritti in (e') ed (f') — `docs/04` §3.

**D28 — La finestra del percentile è 4 anni; sotto i 3 anni la regola non è valida.** *(2026-09-20, decisa)*
Verificata a 3, 4 e 5 anni: le date chiave restano classificate allo stesso modo e i cambi di stato sono il 6,8 % e il
2,4 %. A 2 anni marzo 2020 non si accende, perché la finestra è più corta di un ciclo di mercato e i due anni
precedenti erano tutti di prezzi bassi. Dichiarata fuori perimetro invece di far finta di niente.

**D29 — In stato straordinario il moltiplicatore non può essere 1,0x.** *(2026-09-20, decisa)*
Minimo 1,5x. Senza questo, per i punteggi appena sopra la soglia l'arrotondamento produceva "fase straordinaria,
versa zero euro": il bot avrebbe detto una cosa e suggerito il contrario.

**D30 — I rendimenti decrescenti entrano nel linguaggio del bot, non nel motore.** *(2026-09-20, decisa)*
Ampiezza dei cicli sui nostri dati: +53.814 % → +11.082 % → +2.021 % → **+692 %**. Il motore non ne risente perché
ragiona a percentili (ai quattro minimi il punteggio resta 0,97 · 0,80 · 0,97 · 0,82 mentre l'MVRV assoluto sale da
0,42 a 0,75), ma il premio sì: il rendimento mediano a 12 mesi dei giorni straordinari passa da +321 % a **+40 %**
nell'ultima fase. Quindi il confronto storico del report (F3.2) cita l'**episodio comparabile più recente**, non la
mediana di tutta la storia, e dice che i cicli si stanno accorciando. Dettagli in `docs/04` §8.

## Telegram (sessione 10, fase F4)

**D31 — Il report quotidiano si manda con la sola libreria standard; la libreria esterna resta per i comandi.** *(2026-09-22, decisa)*
Precisa D21 dopo averci messo le mani: mandare un messaggio è una POST HTTPS di dieci righe
(`bot/telegram_client.py`, solo `urllib`). Far dipendere **il messaggio più importante del progetto** da una
libreria esterna significherebbe che può rompersi per un aggiornamento di pacchetto o un venv non attivato sul
VPS. `python-telegram-bot` resta la scelta per i comandi interattivi (F4.2): è la parte che, se si rompe, non
impedisce al report di arrivare.

**D32 — Il bot si chiama AphroditeBTC (@AphroBtcbot).** *(2026-09-22, decisa)*
Tagline scelta dall'utente: *"Love the asset. Analyze the market."* — che è anche il perimetro del progetto:
affezionarsi all'asset, analizzare il mercato, non innamorarsi della previsione.

**D33 — Il registro giornaliero parte dal primo giorno di esercizio.** *(2026-09-22, decisa, era la proposta P1)*
Una riga al giorno in SQLite: data, stato, punteggi, moltiplicatore, prezzo, tutti gli indicatori e il messaggio
inviato. Dieci righe di codice oggi; fra dodici mesi è l'unico modo per fare l'autopsia di D20, e non è
ricostruibile a posteriori.

## Google Trends e formato dei messaggi (sessione 11)

**D34 — Google Trends entra come CONTESTO nel messaggio, non come ingrediente del motore.** *(2026-09-22, decisa)*
Testato sui dati prima di decidere (regola di CLAUDE.md §7). Cosa dicono i numeri, serie mensile 2015→2026
ricucita su due finestre (`data/google_trends_bitcoin.csv`):
- **funziona come misura di affollamento**: rendimento mediano a 12 mesi per livello di interesse —
  sotto 10: **+161 %** (100 % positivi) · 10-20: +95 % · 20-35: +26 % · **35-60: −21 % (13 % positivi)**;
- **non funziona come allarme sui massimi**: il picco di ricerche ha anticipato il massimo di prezzo di
  15 giorni nel 2017, ma di **280 giorni nel 2021** e **339 nel 2025**;
- **si sgonfia come tutto il resto**: 100 (dic 2017) → 51 (apr 2021) → 34 (nov 2021) → 32 (ott 2025);
- **limiti della fonte**: l'indice è riscalato 0-100 sulla finestra richiesta (due tirate diverse non sono
  confrontabili), per finestre lunghe è **mensile**, e `pytrends` non è un'API documentata ma un endpoint
  interno ricostruito — al limite di D2. Per questo il bot **legge solo il CSV**: l'aggiornamento è un passo
  separato (`backtest/aggiorna_google_trends.py`), e se Google cambia qualcosa il report arriva lo stesso.
Farlo entrare nel punteggio richiede di ricalibrare le soglie e **rifare il test di accettazione F2.3** con
otto ingredienti: è il prossimo esperimento, non una modifica da fare di straforo.

**D35 — L'analisi completa ha un formato a sezioni.** *(2026-09-22, decisa)*
Su richiesta dell'utente, ispirato al suo vecchio report `/crypto` (ora in `docs/spunti/`): STATO · PREZZO ·
MVRV · MOMENTUM · ATTENZIONE DELLA GENTE · COSA VARREBBE FARE · ONESTÀ · PRECEDENTE PIÙ RECENTE · dati usati.
Il **polso quotidiano resta di due righe**: è quello che si legge ogni giorno per mesi, e deve restare corto.

**D36 — La BTC dominance resta fuori: testata e scartata.** *(2026-09-22, decisa)*
Proposta dell'utente, con una tesi corretta: se la dominance scende è alt season, cioè fine ciclo. I dati le
danno ragione come *descrizione* — giorni con dominance in calo (−3 punti in 90 giorni) seguiti da 12 mesi a
**+42 %** mediano contro +108 % dei periodi stabili; livello alto → +154 % (88 % positivi), livello basso →
+31 % (61 %). Ma come **ingrediente del motore fallisce la prova di valore aggiunto**: dentro le fasi care la
dominance alta vale +100 % contro +37 %, dentro le fasi molto economiche si **ribalta** (+48 % contro +112 %).
Un segnale che cambia segno da una banda all'altra sta misurando l'epoca, non il mercato: la media annuale del
nostro paniere va da 78 % (2015) a 45 % (2018) a 75 % (2026).
In più la dominance gratuita è **sbagliata nel livello**: il paniere community di CoinMetrics non contiene SOL,
BNB, TRX e altri, quindi dà ~75 % dove la BTC.D vera sta intorno al 58 %. Mostrarla nel messaggio sarebbe
peggio che tacerla. Infine il punto di scopo: la dominance risponde a "BTC o alt?", il bot risponde a "quanto
dei 200 €/mese metto in BTC" — e l'utente le alt non le compra (fuori perimetro, come da charter).
Dati della prova: `data/coinmetrics_basket_mcap.csv` (13 monete, 2015→2026, solo ricerca).

> **Seguito (2026-09-22, stessa giornata).** Obiezione giusta dell'utente: la dominance è un rapporto, quindi va
> testata contro un rapporto (ETH/BTC), non contro il rendimento assoluto di BTC. Rifatto il test:
> con dominance **alta**, ETH/BTC a +12 mesi ha fatto **+233 % mediano (ETH batte BTC nel 90 % dei casi)**; con
> dominance **bassa**, −32 % (11 %). Ma **la direzione è l'opposto della tesi comune**: dopo 90 giorni di
> dominance in calo ("alt season in corso") ETH/BTC nei 12 mesi dopo ha fatto **−6,9 %** — la rotazione va
> anticipata, non inseguita.
> **Il controllo che ridimensiona tutto**: quei giorni sono **6 episodi**, e il +233 % dipende quasi solo dal
> primo (ago 2015 → mar 2016, +304 %: ETH appena nato, da 1,2 a 10 $). Gli altri: +25 %, −5 %, +30 %, +12 %.
> In più la dominance calcolabile gratis è inflazionata: 75 % nel nostro paniere contro il **58,9 % reale**
> (CoinGecko, verificato oggi), perché mancano SOL, BNB, TRX.
> Conclusione invariata per questo progetto (il bot compra solo BTC), ma la logica contrarian sul **livello**
> è annotata: se un giorno si farà qualcosa sul rapporto ETH/BTC, si parte da qui e serve una serie di BTC.D
> vera. Dati: `data/coinmetrics_eth_price.csv`, `data/coinmetrics_basket_mcap.csv` (solo ricerca).

## Comandi e accessi (sessione 12)

**D37 — I comandi Telegram usano la libreria standard, non `python-telegram-bot`.** *(2026-09-22, decisa)*
Completa D21/D31: i comandi sono dieci e il ciclo di long polling sta in un centinaio di righe
(`bot/comandi.py`), quindi sul VPS non serve nessun venv. Se un giorno servissero tastiere, bottoni o
conversazioni a più passi, la scelta si riapre — ma per ora la libreria aggiungerebbe solo una dipendenza da
tenere aggiornata sul percorso più critico del progetto.

**D38 — Il bot è personale: elenco di autorizzati gestito dai comandi.** *(2026-09-22, decisa)*
Chiunque può scrivere a @AphroBtcbot (Telegram non lo impedisce), ma il bot **risponde solo a chi è in
elenco**. Il proprietario è il `chat_id` in `bot/.env` e non è revocabile. A uno sconosciuto il bot dice solo
il suo identificativo, così può chiederlo; `/id` funziona per tutti; `/utenti`, `/autorizza <id>` e
`/revoca <id>` solo per il proprietario. Il **report quotidiano resta al proprietario**: gli autorizzati hanno
i comandi, non le notifiche.

**D39 — Modalità silenziosa.** *(2026-09-22, decisa)*
`/silenzioso` fa scrivere il bot **solo quando cambia lo stato** (cioè quando si accende una fase come giugno
2026); il resto viene registrato e taciuto. `/quotidiano` riporta al battito di ogni giorno. È la risposta alla
richiesta dell'utente di non essere disturbato tutti i giorni, senza perdere il logging (D33).

**D40 — Il messaggio racconta la giornata con una "vista", non solo con lo stato del motore.** *(2026-09-22, decisa)*
Revisione esterna (un altro modello), verificata sui dati prima di accettarla. Il difetto: ai due massimi più
recenti (08/11/2021 e 06/10/2025) lo stato era "normale" perché il freno richiede 60 giorni di fila (D27), ma il
punteggio caro era **0,41 e 0,43** contro una soglia di 0,23 — e il messaggio diceva "⚪️ nessun estremo" nel
giorno esatto del massimo di ciclo. Verificato: freno acceso sulla serie live solo 20/12/2020→19/04/2021 e 5
giorni ad aprile 2024; serie calda più lunga prima di ottobre 2025: 23 giorni.
Soluzione, **senza toccare motore né soglie** (nessuna ri-taratura):
- 🟠 **caldo**: stato normale ma punteggio caro sopra soglia. "Niente extra, il freno scatta a 60 giorni, non è
  un segnale di vendita". Acceso ai due massimi recenti, ma anche a dicembre 2020 prima che il prezzo
  triplicasse: per questo non dice mai "vendi". Capita il **14 %** dei giorni (non il 20 % stimato nella
  revisione), quindi non manda notifiche di cambio stato;
- 🟡 **straordinario in arrivo** — trovato da un test scritto per il caldo: il caso speculare. Punteggio
  economico già sopra soglia ma stato non ancora confermato (servono 2 giorni). Il 05/06/2026, il giorno prima
  dello straordinario di giugno, il messaggio diceva "nessun estremo";
- "**nessun estremo**" solo quando entrambi i punteggi sono sotto soglia; il polso parla della soglia **più
  vicina**, non sempre di quella economica;
- la sezione "l'ultima volta così" solo per straordinario, in arrivo, freno e caldo: "normale" vale l'83 % dei
  giorni e "l'ultima volta normale" non è un precedente.

## Futuro e passato: niente sbirciate, niente adattamenti (sessione 12)

**D41 — Lookahead eliminato e provato; parametri congelati da qui in avanti.** *(2026-09-22, decisa)*
Domanda dell'utente: "il bot sa tutto lo storico, non vorrei che facesse overfitting su un passato che conosce,
mentre il dato di domani non lo sa nessuno". Due problemi distinti, due prove:

*1. Il calcolo usa il futuro?* **Sì, c'era una perdita**, trovata tagliando lo storico a un giorno X e
ricalcolando: stato identico, punteggi no. Causa: RSI settimanale e media a 200 settimane decidevano quali
settimane fossero chiuse guardando la domenica della settimana in corso — cioè il futuro — e così saltavano
l'ultima settimana chiusa. Il bot live (che vede solo fino a oggi) calcolava la cosa giusta; il test storico no.
Corretto riconoscendo la settimana dal calendario (`indice_settimana`), e **reso permanente**
`tests/test_lookahead.py`: taglia lo storico in otto giorni scelti e pretende ogni indicatore, stato e punteggio
identici. Precisazione onesta: la versione vecchia **non leggeva prezzi futuri**; a metà settimana escludeva
l'ultima settimana chiusa, e questo dipendeva dal fatto che nello storico esistessero già i giorni successivi. Era
quindi un indicatore leggermente sbagliato e diverso da quello del bot live, non un vantaggio "rubato" al futuro:
il calo dei risultati qui sotto è l'effetto di aver corretto l'indicatore, non la prova che prima si barasse.
Effetti: soglie ricalibrate con lo stesso metodo
(solo quota di giorni) **0,4229 → 0,4257** e **0,2314 → 0,2315**; criteri ancora 9/9; simulazione **+13,0 % →
+12,3 %** di BTC, tempismo **+2,3 % → +1,8 %**. Numeri dei documenti corretti: giorni sotto la 200-WMA nel 2022
**174 → 177** (anche nel testo dei messaggi), quota di giorni sotto la 200-WMA 8,3 % → 8,6 %, RSI settimanale ai
massimi 90,2/74,1/70,0/65,1 → 90,4/74,2/70,2/65,2. Le note di sessione precedenti restano com'erano.

*2. La regola è adattata a un passato che conoscevamo?* In parte sì, per costruzione: giugno 2026 era il caso che
ha fatto nascere il progetto, quindi "si accende a giugno" **non** è una prova indipendente. La prova onesta è
fuori campione (`backtest/test_fuori_campione.py`): soglie calibrate solo sul passato, congelate, e giudicate su
anni mai visti.
- calibrate fino al **2018** → sul 2019-2026: straordinario il 13,6 % dei giorni; si accende a marzo 2020,
  novembre 2022 e **giugno 2026**; **mai** nei 90 giorni prima dei tre massimi successivi; +12 mesi mediana
  **+73 %** (91 % positivi) contro +48 % di un giorno qualsiasi;
- calibrate fino al **2020** → sul 2021-2026: stessi esiti, +40 % contro +21 %;
- calibrate fino al **2022** → soglia **0,51** e sul 2023-2026 straordinario solo l'**1,1 %** dei giorni (giugno
  2026 acceso 5 giorni). **Fragilità dichiarata**: la soglia dipende da quanti mercati orso contiene il campione di
  calibrazione — il 2022, lungo e profondo, alza l'asticella.

**Regola da oggi**: i parametri del motore sono **congelati**. Una modifica futura si giudica **solo sui giorni
successivi alla modifica** (il registro di D33), mai rifacendo il test storico su un passato già visto — perché
su quel passato si può sempre far vincere qualunque regola. Il registro non si riscrive mai: dice cosa il bot ha
detto quel giorno, con il codice di quel giorno.

**D42 — I confronti coi 4 anni si dicono con i giorni veri e in un verso solo.** *(2026-09-23, decisa)*
Richiesta dell'utente, leggendo sul telefono "negli ultimi 4 anni solo 26 giorni su 100 erano più cari di oggi":
"che vuol dire, in 4 anni non sono 100 giorni". Aveva ragione due volte: "su 100" fa pensare a cento giorni veri,
e il verso cambiava da una riga all'altra ("più cari" per il Mayer, "più economici" per MVRV e 200-WMA).
Forma approvata dall'utente, ora usata in analisi completa, "Perché:" dei cambi di stato, `/perche` e guida:
**"negli ultimi 4 anni è stato più alto di oggi in 386 giorni su 1.460 (26%)"**. Giorni contati davvero da
`messaggi.quanti_piu_alti` sulla stessa finestra e con lo stesso minimo del motore (niente lookahead, provato);
accanto "zona cara" / "zona economica" quando l'indicatore entra nel punteggio, con le parole di "spingono:".
I pareggi si dicono quando pesano almeno l'1% — trovato dal test: il 30/12/2020 il drawdown era a 0 come in altri
121 giorni, e "il valore più alto" avrebbe fatto credere a un caso unico. Nessun numero del motore cambia: è solo
testo. Test permanenti in `tests/test_d42_frasi.py` (fra cui: più alti + uguali + più bassi = tutti gli altri
giorni, esatto, per sette indicatori e sei date). Corretto anche "e altri 1" → "e un altro".

**D43 — Repository git e messa in esercizio sul VPS con systemd; il progetto si chiama AphroditeBTC.** *(2026-09-26, decisa)*
Dal 22/09 il bot non è mai partito (registro con una riga sola): il limite non era il codice, era che partisse a mano
dal PC. Approvato dall'utente: repository git (primo commit `bdddac1`; esclusi `bot/.env`, il database e
`docs/spunti/`), remoto GitHub privato `AphroditeBTC`, e i file di `deploy/`. L'ascolto è un servizio sempre acceso
che riparte da solo; il report ha un timer alle 09:00 **Europe/Rome** (il cambio d'ora lo gestisce systemd: con
l'orario in UTC, dopo il 25 ottobre sarebbe arrivato alle 8); il backup notturno usa l'API di SQLite, controlla
l'integrità e tiene 30 copie. Il VPS legge il repository con una deploy key di sola lettura; token e database
viaggiano via `scp`, mai da GitHub. Un solo ascoltatore per bot (Telegram risponde 409 Conflict al secondo): i `.bat`
del PC restano come riserva. Nome di repository, cartella sul VPS e servizi: **AphroditeBTC**, come il bot.
Corretto `bot/requirements.txt`: nessuna dipendenza (D37 aveva già superato D21). Aggiunto `bot/.env.example`.

## Proposte non ancora confermate

**P1 — Logging dal giorno 1.** *(2026-09-20, proposta → **confermata come D33 il 2026-09-22**)*
Il bot registra ogni giorno prezzo, tutti gli indicatori calcolati e il messaggio inviato. Dieci righe di codice oggi;
fra dodici mesi è l'unico modo per fare l'autopsia prevista dall'analisi. Non è ricostruibile a posteriori.

**P2 — Primo messaggio Telegram reale entro due settimane.** *(2026-09-20, proposta → **fatta il 2026-09-22**, due giorni dopo)*
Anche con i soli indicatori già validati, per uscire dalla fase di sola analisi: il progetto ha prodotto quattro documenti
e zero bot in funzione. Gli indicatori restanti si innestano su qualcosa che già gira.

## Aperte (non bloccano il bot di report)

Le sei domande del §9 dell'analisi v5.1, meno l'hosting che è stato deciso (D13):

0. **Il tetto dello sforzo straordinario per ciclo** (F2.5), in mesi equivalenti di budget: è l'unico parametro che
   dipende da quanto l'utente può permettersi e non dai dati. La simulazione dice che non è mai stato un vincolo a 12
   mesi equivalenti (ciclo più intenso: 6,9 usati su 12) e che a 6 comincia a mordere. Finché non è deciso, il bot lo
   dichiara invece di inventarlo.
1. **Exchange e fee reali** — Binance/Kraken (~0,1 %) o un'app tipo Revolut (~1,5 % + spread)?
2. **Fiscalità** — le plusvalenze sono davvero irrilevanti? Se no, entra un parametro `tax_rate` e il break-even del SELL peggiora. *(Non necessaria alla v1: vedi D18.)*
3. **Valuta degli ordini** — EUR probabile; gli indicatori restano su BTC-USD.
4. **SELL nel v6** — spento di default e sperimentale (raccomandazione dell'analisi) o nel primo rilascio?
5. **Orizzonte di paper-trading** prima di mettere soldi sul SELL.
