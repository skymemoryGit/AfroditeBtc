# Piano di sviluppo — Bot BTC "report e sforzo"

Versione 1 · 2026-09-20 (sessione 05) · Charter approvato punto per punto dall'utente.
Prerequisiti già pronti: indicatori validati (`botbtc/indicators.py`), dati storici in `data/`, decisioni in `docs/00_decisioni.md`.

---

## 0. Cosa costruiamo, in una pagina

Un bot Telegram che guarda BTC ogni giorno al posto dell'utente e classifica il mercato in **tre stati di sforzo**:

| stato | significato | cosa dice il bot |
|---|---|---|
| **straordinario** | zona storicamente rara ed economica | "varrebbe un versamento extra, in più colpi: qui è successo N volte dal 2017, dopo 12 mesi …" |
| **normale** | nessun estremo | i 200 €/mese e basta |
| **freno** | zona storicamente cara | "non è una fase da versamenti straordinari: tieni il ricorrente e aspetta" |

Il bot **non esegue ordini, non vende e non custodisce soldi**. In stato di freno non dice mai "vendi": dice solo di non
aggiungere. Se l'utente decide di alleggerire per conto suo, è una sua scelta, fuori dal perimetro del bot.

Tre modi di parlare: **A)** analisi completa su richiesta, in qualsiasi momento · **B)** polso regolare, due righe,
silenzioso · **C)** messaggio d'eccezione quando lo stato cambia.

**Obiettivo di consegna: primo messaggio reale ricevuto su Telegram entro due settimane** (fasi F0-F2 + F4 minima).
Il resto si innesta su qualcosa che già gira.

---

## F0 — Fondamenta (mezza serata)

**F0.1** Creare `bot/` con `main.py` (entry point), `config.py` (tutti i parametri: budget mensile, moltiplicatori,
soglie, chat_id, orari) e `.env` per il token Telegram — `.env` è già in `.gitignore`.
*Verifica*: `python3 bot/main.py --dry-run` parte, legge la configurazione e stampa i parametri senza toccare la rete.

**F0.2** Decisione minore da prendere qui: libreria Telegram o `urllib` della libreria standard.
Raccomandazione: **urllib** — il progetto non ha dipendenze e il deploy sul VPS resta banale; mandare messaggi e leggere
i comandi in long-polling sono poche decine di righe. Se preferisci coerenza con gli altri tuoi bot, si usa la libreria.
*Verifica*: scelta scritta in `docs/00_decisioni.md`.

## F1 — Strato dati (una serata)

**F1.1** Fetcher per le tre fonti: prezzo (Coinbase, fallback Binance), Fear & Greed (alternative.me),
MVRV (CoinMetrics Community). Ogni fetcher restituisce dati **o** un errore esplicito: mai un valore inventato.
*Verifica*: staccando la rete, ogni fetcher fallisce in modo pulito con un messaggio leggibile.

**F1.2** Cache locale in SQLite, che è anche l'archivio storico: al primo avvio si carica dai CSV in `data/`, poi si
aggiorna ogni giorno con il dato nuovo.
*Verifica*: due esecuzioni di fila — la seconda non richiama la rete; il numero di righe cresce di uno al giorno.

**F1.3** Controlli di sanità: buchi nella serie, salti di prezzo oltre il 30% in un giorno, timestamp fuori ordine,
e il caso specifico del **ritardo MVRV** (il dato del giorno T arriva il giorno T+1).
*Verifica*: iniettando a mano una riga sballata, il controllo la intercetta e il bot lo segnala invece di proseguire.

**F1.4** Ponte con gli indicatori: `botbtc/indicators.py` calcola tutto dalla cache, senza dipendenze nuove.
*Verifica*: gli indicatori calcolati sulla data di sovrapposizione coincidono con quelli di `validate_mvrv.py`.

## F2 — Il motore degli stati (una serata) — **è il cuore del progetto**

> **FATTA il 2026-09-20 (sessione 07).** Risultati, parametri, prove e limiti: `docs/04_regola_stati.md`.
> Esito: **9 criteri operativi su 9**, dopo aver riscritto (e) ed (f) — erano incompatibili fra loro, la prova
> coi numeri è in `docs/04` §3 ed è stata approvata dall'utente. Codice: `botbtc/engine.py`;
> test: `backtest/test_storico_stati.py`, `backtest/simula_sforzo.py`, `tests/test_f2.py`.

**F2.1** Funzione pura `stato(indicatori_del_giorno) -> (stato, motivi, moltiplicatore_suggerito)`, senza effetti
collaterali, usata identica dal bot e dai test storici. Nessun lookahead.
*Verifica*: stessa funzione, stesso input, stesso output; nessun accesso a rete o file al suo interno.

**F2.2** Regole **a percentile, non a soglia assoluta** (il percentile a 4 anni è l'unica misura che resta confrontabile
fra cicli: coefficiente di variazione 0,069 contro 0,5 dello Z-score). Ingredienti: percentile MVRV, MVRV grezzo,
Mayer, prezzo/200-WMA, drawdown dal massimo annuale, RSI giornaliero e settimanale, F&G. Pi Cycle solo come contesto.
*Verifica*: cambiando ciclo di mercato le regole non vanno ritarate a mano.

**F2.2-bis — come si combinano gli ingredienti** (aggiunto dopo la seconda revisione esterna: è il punto in cui questo
motore può fallire in silenzio). Un **AND stretto** su tutti gli indicatori fa sì che giugno 2026 possa *non* accendersi
pur col prezzo sulla 200-WMA, perché basta un ingrediente fuori posto; un **OR largo** accende nel 20-30 % dei giorni e
il bot diventa rumore che silenzi dopo due settimane. Quindi né l'uno né l'altro: **punteggio di profondità**, in cui
ogni indicatore contribuisce in base a quanto è estremo, con una soglia calibrata **solo** sul criterio (c) di F2.3
(quota di giorni), mai sulle date che vogliamo far accendere. Il contatto con la 200-WMA, che da solo è un evento
all'**8,6 % dei giorni dal 2014**, deve poter pesare abbastanza da accendere lo stato anche quando gli altri sono tiepidi.
*Verifica*: contare i giorni accesi con le tre logiche (AND, OR, punteggio) e metterle in tabella: la scelta si
giustifica con i numeri, non a intuito.

**F2.3 — Test di accettazione storico. Questo è il test che decide se il progetto funziona.**
Si fa girare la funzione su tutta la storia 2017→2026 e si guarda cosa avrebbe detto giorno per giorno.
Criteri: **(a) giugno 2026 deve risultare "straordinario"** — è il caso che ha fatto nascere il progetto, se non si
accende la regola è sbagliata; **(b)** devono accendersi anche dicembre 2018, marzo 2020 e novembre 2022;
**(c)** lo stato "straordinario" non deve superare il 10-15% dei giorni, altrimenti non è un'eccezione ma rumore;
**(d)** nessun singolo giorno di "straordinario" nei tre mesi precedenti un massimo di ciclo.

Criteri aggiunti dopo la revisione esterna del 2026-09-20 — i primi quattro mettono alla prova solo lo stato
*straordinario*, e uno stato che non viene mai testato finisce calibrato per non sbagliare invece che per servire:

> **RISCRITTO (2026-09-20).** I criteri (e) ed (f) qui sotto sono risultati **incompatibili fra loro**: a fine
> dicembre 2020 il mercato era più caro, su ogni ingrediente, di quanto fosse ai massimi del 2021 e del 2025, quindi
> nessuna soglia sul livello può accendersi a quei massimi e restare spenta lì. Restano scritti qui come storia;
> valgono le versioni (e') ed (f') di `docs/04` §3: il freno dev'essere **raro e informativo** (≤ 10 % dei giorni,
> ≥ 60 % dei suoi giorni entro 12 mesi da un massimo, rendimento mediano a 12 mesi negativo) e **quasi muto a inizio
> rialzo** (≤ 5 giorni in novembre-dicembre 2020).

**(e) Il freno deve cogliere qualcosa.** Deve risultare acceso nei tre mesi che precedono almeno **tre dei quattro
massimi moderni** (2017-12-16, 2021-04-13, 2021-11-08, 2025-10-06 — l'ultimo è un massimo *presunto*, vedi `docs/02` §2:
va trattato come tale e non deve da solo far passare o fallire il test). Se il freno non si accende mai vicino a un
massimo, è uno stato decorativo e va tolto.

**(f) Ma il freno non deve frenare troppo.** Non più del 20-25 % dei giorni, e soprattutto **non acceso nelle fasi
iniziali di un rialzo**. Controllo specifico e non negoziabile: **novembre-dicembre 2020**, quando la v5.1 cominciò a
vendere a 16-19 mila dollari e il prezzo andò a 60 mila. Se il freno si accende lì, sta ripetendo esattamente l'errore
che abbiamo già pagato nel backtest.

> **ESITO (2026-09-20).** Superato a 3, 4 e 5 anni (cambi di stato 6,8 % e 2,4 %, stesse date accese). A 2 anni
> marzo 2020 non si accende: finestra più corta di un ciclo, **dichiarata fuori perimetro** (D28).

**(g) Sensibilità alla finestra del percentile.** Il test si rifà con finestre a **2, 3, 4 e 5 anni**: le date chiave
devono restare classificate allo stesso modo, e la quota di giorni che cambia stato passando da una finestra all'altra
deve restare sotto una soglia dichiarata (proposta: 15 %). Motivo tecnico: la finestra di 4 anni è **circa la lunghezza
di un ciclo di mercato**, quindi il percentile rischia di essere in parte auto-referenziale — ogni ciclo produce per
costruzione i propri decili bassi vicino al proprio minimo. Se il risultato regge solo a 4 anni, dipende da un
iperparametro fortunato e non da una proprietà del mercato.

**Regola procedurale (vale più dei criteri stessi).** I parametri della regola si fissano e si **scrivono prima** di
lanciare il test storico, partendo dai principi e dai numeri di `docs/02`, non dalle date che vogliamo veder accendere.
Solo dopo si guarda il risultato. Ogni ri-taratura fatta *dopo* aver visto l'esito va annotata nella nota di sessione con
un contatore: se servono più di due o tre giri, la regola non sta descrivendo il mercato, sta imparando a memoria il
passato — e a quel punto giugno 2026 non è più una verifica, è un aneddoto automatizzato.

**F2.4** Moltiplicatore dello sforzo: da stato a numero concreto ("questa settimana varrebbe 2-3 volte il normale"),
con la regola che l'extra si mette **in più colpi**, mai in uno.
*Verifica*: simulando i 177 giorni sotto la 200-WMA del 2022, il bot non suggerisce mai di esaurire tutto al primo giorno.

> **ESITO F2.4/F2.5 (2026-09-20).** Simulazione 2015-2026 in `docs/04` §5: tranche massima 100 € (4,2 % del tetto),
> sforzo spalmato su almeno 3 tranche in tutti i cicli, tetto mai superato, capienza sempre residua al punto più
> profondo. A parità di depositi il tempismo aggiunge **+1,8 %** di BTC; il beneficio vero è aver versato di più
> (+12,3 % di BTC con +10,3 % di soldi; numeri dopo la correzione D41). **Resta da decidere solo il valore del tetto.**

**F2.5 — Tetto complessivo dello sforzo straordinario (aggiunto dopo la revisione esterna).**
Un moltiplicatore senza tetto è market timing emotivo con un'interfaccia elegante: se il bot dice "straordinario" per
sessanta giorni di fila mentre il prezzo scende, senza un limite dichiarato in anticipo si finiscono i soldi o si
smette di credergli. Quindi: si dichiara **prima** un tetto di versamenti straordinari **per ciclo**, espresso in
**mesi equivalenti di budget** (es. "12 mesi equivalenti" = 12 × budget mensile), così resta valido anche passando da
200 a 500 €/mese. Il bot lo tiene a libro e lo dice in ogni messaggio di stato straordinario: "usati X di Y".
Il moltiplicatore smette di essere un numero libero e diventa **l'allocazione di quel tetto in tranche legate alla
profondità del percentile**, con le tranche più grandi riservate ai decili più bassi — coerente con i dati: il decile
più basso dell'MVRV ha dato mediana +127 % a 12 mesi, il decile 10-25 +83 %.
*Verifica*: nella simulazione storica il bot non spende mai più del tetto in un ciclo, e — controllo più importante —
arrivando al decile più basso deve avere ancora capienza: se il tetto si è esaurito prima, le tranche sono tarate male.
*Da decidere dall'utente*: il valore del tetto. È l'unico parametro del progetto che dipende da quanto può permettersi,
non dai dati.

**F2.6 — Nucleo "solo prezzo" e degrado con grazia (aggiunto dopo la seconda revisione esterna).**
Gli ingredienti non arrivano tutti insieme: MVRV ha un giorno di ritardo strutturale e il Fear & Greed dipende da una
fonte terza, mentre **Mayer, 200-WMA, drawdown 365 e RSI si calcolano dal solo prezzo, disponibile subito**. Il caso che
ha fatto nascere il progetto — contatto con la 200-WMA — è per l'appunto un evento di puro prezzo. Quindi il motore
calcola **due livelli**: un *nucleo* con i soli indicatori di prezzo, sempre disponibile, e una versione *arricchita*
con MVRV e F&G quando ci sono. Se le fonti lente mancano o sono vecchie, il bot **parla lo stesso** usando il nucleo e
dichiara con quali ingredienti ha deciso; non tace e non aspetta, perché ritardare l'unico allarme utile è il modo
peggiore di fallire. Il ritardo di un giorno su un segnale che dura mesi è irrilevante: il problema non è la velocità,
è la disponibilità.
*Verifica*: simulando CoinMetrics irraggiungibile per tre giorni, il bot continua a mandare il messaggio, la riga degli
ingredienti dice cosa manca, e lo stato calcolato dal nucleo non è mai "sconosciuto".

## F3 — Il testo dei messaggi (una serata)

**F3.1** Tre formati: polso breve (due righe), cambio di stato (esteso, con il perché), analisi completa a richiesta.
Il polso è **quotidiano** e non è decorazione: se l'ingresso in zona è un avvicinamento lento — come fu giugno 2026 — un
singolo messaggio di cambio stato può passare inosservato fra le notifiche, mentre il battito giornaliero è la rete di
sicurezza. Per questo il polso contiene anche una **riga di avvicinamento** ("a +4 % dalla 200-WMA, in calo da 9 giorni"),
che mostra la distanza dalle soglie e la direzione: il bot segnala che ti stai avvicinando, non solo che sei arrivato.
*Verifica*: il polso sta in due righe anche nei giorni noiosi; l'analisi completa non supera un messaggio Telegram;
rigenerando i polsi dei 30 giorni prima di giugno 2026 si vede la distanza dalla 200-WMA ridursi giorno per giorno.

**F3.2** Confronto storico automatico: "l'ultima volta in questa situazione era il …, dopo 6/12 mesi BTC ha fatto …",
calcolato dai dati, mai scritto a mano. **Vincolo aggiunto il 2026-09-20 (D30):** si cita l'**episodio comparabile
più recente**, non la mediana di tutta la storia — l'ampiezza dei cicli si sta riducendo (+53.814 % → +11.082 % →
+2.021 % → +692 %) e con essa il premio (mediana a 12 mesi dei giorni straordinari: +321 % nella prima fase, **+40 %
nell'ultima**). Citare la mediana storica significherebbe promettere un mondo che non c'è più.
*Verifica*: su tre date campione il numero citato si ritrova rifacendo il conto a mano dai CSV.

**F3.3** Regola dell'onestà: ogni messaggio di stato "straordinario" dice anche che la zona può durare e peggiorare
(nel 2022: 177 giorni sotto la 200-WMA, fino a −34%). Ogni messaggio dichiara la data del dato MVRV usato.
*Verifica*: generare i messaggi per 10 date storiche (dic 2018, mar 2020, nov 2021, nov 2022, ott 2025, giu 2026 …),
stamparli e leggerli: si capiscono? dicono anche i limiti? non sembrano ordini?

## F4 — Telegram e consegna (una serata)

**F4.1** Invio del messaggio all'orario stabilito, con il dato MVRV del giorno prima dichiarato come tale.
*Verifica*: il messaggio arriva davvero sul telefono, all'ora giusta.

**F4.2** Comandi: `/analisi` (modalità A, completa), `/stato` (il polso, su richiesta), `/perche` (come è stato
calcolato lo stato di oggi), `/pausa` e `/riprendi`.
*Verifica*: `/analisi` risponde in meno di cinque secondi anche partendo da cache fredda.

**F4.3** Gestione errori: se una fonte manca all'orario del report, il messaggio lo dice e non mostra valori vecchi
come se fossero di ieri.
*Verifica*: simulando una fonte giù, arriva il messaggio con l'avviso, non il silenzio e non un numero stantio.

## F5 — Messa in esercizio sul VPS Contabo (mezza serata)

**F5.1** Deploy con systemd timer (non cron: log migliori e ripartenza pulita), utente dedicato, cartella dati fuori
dal codice.
*Verifica*: riavviando il server il timer riparte da solo.

**F5.2** Log applicativo e rotazione; backup periodico del database (è la memoria del punto 12 del charter).
*Verifica*: cancellando il database di prova, il backup lo ripristina.

## F6 — Esercizio e paper-trading (12 mesi, zero lavoro quotidiano)

**F6.1** Ogni giorno il database registra prezzo, **tutti** gli indicatori, lo stato e il messaggio inviato.

**F6.2** In silenzio, una riga in più: cosa avrebbe detto una regola di **alleggerimento** (paper-trading, nessun
messaggio, nessuna esecuzione). Serve a decidere fra dodici mesi con dati veri invece che con opinioni.

**F6.3** Autopsia a 3, 6 e 12 mesi: il bot ha parlato nei momenti che col senno di poi erano buoni? Hai fatto almeno un
acquisto straordinario grazie a lui? Se la risposta è no a dodici mesi, si spegne o si cambia — come previsto dal charter.

## F7 — Presentazione per il cliente (aggiunta il 2026-09-22 su richiesta dell'utente)

Il bot va consegnato come se lo ricevesse **qualcuno che non ha nessun contesto**: niente sessioni, niente
indicatori, niente gergo. Serve una presentazione che spieghi *l'obiettivo* prima del *come*.

**F7.1** Appunti dei contenuti, slide per slide, con i numeri verificati e la fonte di ognuno.
*Verifica*: ogni numero degli appunti si ritrova in `docs/` o rilanciando uno script di `backtest/`.
*(Iniziata il 2026-09-22: `docs/06_appunti_presentazione.md`.)*

**F7.2** Spiegazioni più semplici di quelle usate con l'utente: la metafora dei "100 giorni in fila" per il
percentile, i "due termometri" per i punteggi, "quanta strada manca" invece dei decimali.
*Verifica*: una persona senza contesto legge la slide dei punteggi e sa dire in che stato è il mercato oggi.

**F7.3** Presentazione PowerPoint (o formato slide equivalente), con grafici veri dai dati: i quattro massimi
che si abbassano, il semaforo dei tre stati, l'esempio oggi contro giugno 2026, il test sulla storia.
*Verifica*: nessun numero inventato; ogni grafico si rigenera dagli script.

**F7.4** Una pagina di "limiti dichiarati": cosa il bot non fa e non sa. È la slide che distingue un prodotto
onesto da una promessa.

---

## Ordine consigliato se hai poche serate

MVP per il primo messaggio reale: **F0 → F1 → F2 → F4.1** (il testo può essere grezzo alla prima passata).
Poi F3 per rendere i messaggi leggibili, F5 per il deploy, e F6 parte da sé.
F2.3 non si salta mai: è il test che distingue un bot utile da uno che parla a caso.

## Rischi e come li teniamo bassi

| rischio | contromisura |
|---|---|
| Le soglie invecchiano di ciclo in ciclo (dimostrato per MVRV, Mayer, RSI-W, Z) | regole a percentile, mai assolute (F2.2) |
| Il bot diventa rumore e lo silenzi | stato normale = due righe silenziose; solo il cambio di stato fa rumore |
| Falso senso di sicurezza ("è raro, metto tutto") | messaggio che dichiara sempre che può peggiorare + sforzo in più colpi (F2.4, F3.3) |
| Fonte dati giù o in ritardo | fallback, cache e messaggio esplicito; mai un valore vecchio spacciato per fresco (F1.3, F4.3) |
| Il progetto resta in fase di analisi | obiettivo dichiarato: primo messaggio entro due settimane |
| "Straordinario" per 60 giorni mentre il prezzo scende: finiscono i soldi o la fiducia | tetto per ciclo dichiarato prima, speso in tranche, saldo mostrato a ogni messaggio (F2.5) |
| Lo stato freno calibrato per non sbagliare mai, quindi inutile | criteri (e) ed (f) di F2.3: deve accendersi vicino ai massimi e non nelle prime fasi di un rialzo |
| La regola funziona solo con la finestra percentile "fortunata" | criterio (g): test di sensibilità a 2/3/4/5 anni |
| Tre-quattro cicli di storia non sono una prova statistica | paper-trading e autopsia (F6) invece di certezze anticipate |

## Fuori perimetro (confermato)

Nessun ordine automatico, nessuna vendita suggerita dal bot, nessun altro asset, nessuna fonte a pagamento,
nessuno scraping. Il bot BUY+SELL "max return" (v6) resta rinviato: se ne riparla dopo l'autopsia.

**Fiscalita' e commissioni di exchange sono fuori perimetro** (deciso il 2026-09-20). E' coerente con il resto: il bot
non esegue ordini e non suggerisce vendite, quindi non c'e' nulla su cui fee e imposte possano incidere; i 200 EUR/mese
e i versamenti straordinari l'utente li esegue come gia' fa oggi. Attenzione pero' a non dimenticarsene dopo: nel giorno
in cui si valutasse davvero un modulo di alleggerimento (F6.2, e poi il v6), fee e imposte tornano a contare e alzano
parecchio l'asticella del vendi-e-ricompra. Restano nella lista delle domande aperte di `00_decisioni.md`, marcate come
non necessarie alla v1.
