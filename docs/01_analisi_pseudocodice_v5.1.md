# Analisi dello pseudo-codice BOT BTC v5.1 (BUY + SELL, "max return")

Data analisi: 2026-09-19 · Sorgente: `bot_btc_v5_1_buy_sell_maxreturn.docx` · Analista: Claude (Fable 5.1)
Stato: **analisi conclusa, piano di sviluppo NON ancora scritto** (prossimo passo, dopo le decisioni in §9).

---

## 0. Verdetto in breve

**Lato BUY (v4: DCA 70% + dip 30%)** — impianto solido, logica chiara, pochi bug reali (§2). Sul backtest 2018→2026 fa
**circa pari con il DCA puro** (da −3,3% a +4,4% di BTC accumulati a seconda della finestra, quasi sempre leggermente sotto).
Non fa danni, ma non è la fonte di extra-rendimento che ci si aspetterebbe: il cash tenuto in riserva costa più di quanto
rendano i dip comprati a sconto.

**Lato SELL (v5.1)** — l'idea è sensata (vendere quote nell'euforia, ricomprare nella paura) ma **così com'è scritto perde
valore**: nelle finestre che contengono l'inizio del bull market 2020-21 il bot finisce con **il 10-16% di BTC in meno del DCA
puro** (e ~13% in meno della v4 senza SELL). La causa non è la lettura del mercato: è un **difetto strutturale** nella
gestione del ricavato (`riserva_sell`): il rientro è tappato da `tetto_singolo` (125 €/settimana, dimensionato sui 200 €/mese)
mentre la riserva vale decine di volte tanto; così nel crash di maggio-luglio 2021 rientrano ~390 $ su 11.400 $, e a
scadenza (4 mesi) il resto viene ributtato dentro come DCA a 47k dopo aver venduto a ~22,5k medi.

**Con tre correzioni strutturali** (rientro proporzionale alla riserva, niente scadenza, soglie di euforia più alte) il modulo
SELL torna positivo (+5,1% vs DCA dal 2018, +2,2% dal 2019) — ma quasi tutto il guadagno viene da **un solo episodio**
(vendita gen-mar 2021, riacquisto giu 2021-giu 2022) e con le soglie alte il top di marzo 2024 non viene colto. Con due cicli
di mercato in campione non c'è evidenza statistica: il SELL va trattato come **modulo sperimentale, spento di default**,
da valutare all'autopsia come già prevede il documento.

**Raccomandazione**: si può procedere al piano di sviluppo, ma per una **v6** con le modifiche di §8, e con il backtester
come primo deliverable (non l'ultimo). Il bot Telegram vale soprattutto per disciplina ed esecuzione; l'alpha del timing su
BTC, per un accumulatore da 200 €/mese, è piccolo e va misurato, non dato per scontato.

---

## 1. Cosa c'è di buono (da tenere)

1. **Umano nel loop, nessuna leva, nessun ordine automatico**: il bot comanda, tu esegui e confermi. Giusto per il tuo caso.
2. **Isteresi ovunque** (trend a 5 giorni, bande con doppia conferma e banda morta): evita il flip-flop settimanale.
3. **Mutua esclusione BUY/SELL** e "mai vendere in downtrend": due guard-rail corretti.
4. **Cap del 50% cumulato**: chi svuota nell'euforia si perde il bull run; il vincolo è sacrosanto.
5. **Audit di conservazione** (nessun euro appare o sparisce) e **guardia ordine pendente**: rari nei bot amatoriali, ottimi.
6. **Confronto a tre** (DCA puro, v4, v5.1) e **autopsia a 12/24 mesi** con regole di spegnimento già scritte. È esattamente
   il metodo giusto — e infatti applicandolo in backtest il verdetto sul SELL è arrivato subito.
7. **Cadenza settimanale con osservazione giornaliera**: coerente con l'orizzonte (cicli di anni) e con un umano che deve eseguire.

---

## 2. Bug e ambiguità nello pseudo-codice

Severità: **B** = bug (produce comportamento sbagliato o rompe l'audit), **A** = ambiguità (due implementatori scriverebbero
due bot diversi), **D** = difetto di design (funziona, ma perde valore).

| # | Sev | Dove | Problema | Correzione proposta |
|---|-----|------|----------|---------------------|
| 1 | **D** | Passo 4, rientro `riserva_sell` | `extra = min(riserva_sell, tetto_singolo − DCA − dip)` → max ~75-90 €/sett. La riserva dopo un bull run vale migliaia di euro: non rientra mai in tempo nel crash e va in scadenza. **È il difetto che da solo spiega il −14% del backtest.** | Rientro proporzionale alla riserva: banda 1 → 15%/sett., banda 2 → 30%, banda 3 → 50% della `riserva_sell` (nessun tetto assoluto per questo flusso). |
| 2 | **D** | Passo 5, scadenza 4 mesi | Il ricavato scaduto diventa DCA "a prezzo qualsiasi". Nel 2021 vuol dire ricomprare a 47k ciò che si era venduto a 21k. Con 4 mesi di orizzonte si sta scommettendo che un crash arrivi entro 4 mesi dal top: storicamente non è vero (top gen 2021 → crash mag 2021 ok; top nov 2020 → nessun crash entro marzo 2021). | Nessuna scadenza automatica: la riserva aspetta `banda_stress ≥ 1`. In alternativa scadenza ≥ 12 mesi. Il "cash fermo = ritorno morto" è vero solo se il prezzo sale: se il modulo SELL ha senso, la riserva deve poter aspettare. |
| 3 | **D** | Passo 4, quote SELL | `vendi = residuo × {10, 20, 30}%` **ogni settimana** finché la banda resta accesa: in banda 3 il 30% del residuo a settimana esaurisce il 50% in 3-4 settimane, sempre nella prima fase dell'euforia (nov 2020: vendite a 16-19k, poi il prezzo fa 60k). | Bande come **obiettivo cumulato**, non come quota settimanale: banda 1 → 15% venduto in totale, banda 2 → 30%, banda 3 → 50%. Si vende solo la differenza tra obiettivo e già venduto. Una banda accesa a lungo non svuota. |
| 4 | **D** | Passo 2, soglie euforia | `+10` a +20% sopra media200 è troppo basso: in un bull market BTC sta sopra +20% per la maggior parte del tempo (2020-21: da +32% a +155%). Le vendite partono all'inizio del rialzo, non nell'eccesso. | Soglie sul Mayer Multiple più alte (es. +50% / +80% / +120% sopra media200 → 1.5× / 1.8× / 2.2×). Nel backtest è la modifica che rende il SELL positivo. Rovescio: il top di marzo 2024 (+84% per una sola settimana) non passa la doppia conferma. |
| 5 | **B** | Passo 4, dip banda 3 | `min(37 €, riserva_dip × 0.4)`: nei primi mesi `riserva_dip = 0` → in pieno crash il dip è **0 €** (il caso in cui serve di più). | `min(37 €, sett_dip + 0.4 × riserva_dip)`: la quota fresca di 15 €/sett. è sempre disponibile, il 40% si applica solo alla riserva. |
| 6 | **B** | Passo 4, banda 0 | `riserva_dip += 15 €` ogni settimana in banda 0, ma `budget_dip_rimasto` non viene decrementato; a fine mese `riserva_dip += budget_dip_rimasto` → **doppio conteggio**, l'audit salta. | Spostare i 15 € da `budget_dip_rimasto` a `riserva_dip` (decremento esplicito), oppure spostare tutto solo a fine mese. |
| 7 | **B** | Passo 4, `compra_DCA = 35 € SEMPRE` | I mesi hanno 4 o 5 lunedì: 5 × 35 = 175 > 140 → budget negativo; e l'anno ha 52 settimane, non 48. Con la regola "fine mese spendi tutto" il totale annuo non torna. | `DCA_settimana = budget_DCA_rimasto / lunedì_rimanenti_nel_mese`. Generalizza 140/4 = 35 e assorbe anche gli extra (surplus riserva, riserva_sell scaduta). |
| 8 | **A** | Passo 2, `base = max(\|cheapness\|, \|dd_ciclo\|)` | `base` è una frazione (0.12) sommata a punti (0-100)? O è inutilizzata? Le righe successive (+50/+30/+10) usano già le stesse soglie. E i tre livelli sono **esclusivi** (if/elif) o **cumulativi**? Se cumulativi, essere −20% sotto media200 vale 90 punti e la banda 3 scatta di continuo. | Eliminare `base`. Dichiarare i livelli **esclusivi** (il massimo raggiungibile diventa 85 = 50+20+15, coerente con la soglia "banda 3 ≥ 85": la calibrazione del documento regge solo con questa lettura). Stessa cosa per l'euforia (max 95). |
| 9 | **A** | Passo 2, mutua esclusione | `se banda_corrente ≥ 1: euforia = 0` — ma `banda_corrente` viene aggiornata nel Passo 3, dopo. È la banda della settimana scorsa? | Specificare: banda stress **di questa settimana** (calcolare prima le bande stress, poi l'euforia). |
| 10 | **A** | Memoria, `stack_venduto_cumulo` | "% cumulata venduta" — percentuale di cosa? Lo stack cresce ogni settimana con il DCA. E il contatore **non si azzera mai**: dopo un ciclo al 50% il bot non vende più per il resto della sua vita. | Definire `totale = stack_BTC + BTC_venduti_nel_ciclo`; vincolo `venduti ≤ 50% × totale`. Reset del ciclo quando la riserva_sell è tornata a zero (tutto ricomprato) e la banda SELL è 0. |
| 11 | **A** | Passo 4, `riserva_sell_prevista` | Variabile mai definita altrove (compare solo nella sottrazione `−= extra`). | Una sola variabile `riserva_sell`; l'impegno "in attesa conferma" va tracciato nell'ordine pendente, non in una seconda riserva. |
| 12 | **B** | Passo 4/5, `carrello_sell` | Se la banda SELL torna a 0 prima di raggiungere `carrello_sell_min`, i BTC "autorizzati" restano nel carrello e verrebbero venduti alla prossima euforia anche minima. | Svuotare `carrello_sell` quando `banda_sell = 0`. |
| 13 | **B** | Passo 6, audit | La formula di `reale` non include `budget_DCA_extra` (riserva_sell scaduta) e assume che l'importo eseguito sia identico a quello ordinato. Con `/fatto <importo_reale>` diverso dall'ordine (arrotondamenti, minimi dell'exchange) l'audit da 1 € scatta a ogni ordine. | Implementare l'audit come **libro mastro** (ogni movimento registrato: deposito, ordine, esecuzione, fee, scadenza) e verificare l'invariante sul mastro. La differenza ordine/eseguito torna esplicitamente nel budget di provenienza. |
| 14 | **A** | Passo 0, ordine pendente | Se l'ordine resta pendente per settimane, il DCA non viene emesso (Passo 0 esce). A fine mese "spendi tutto" con un ordine pendente: comportamento indefinito. | Promemoria giornaliero; comando `/annulla`; dopo N giorni l'ordine decade e i soldi tornano al budget. Il DCA settimanale continua ad accumularsi nel carrello anche con ordine pendente (verrà emesso alla conferma). |
| 15 | **A** | Routine giornaliera / prezzo | Prezzo in USD o EUR? RSI su chiusure giornaliere di quale exchange? Il F&G è calcolato su BTC/USD. | Indicatori su **BTC-USD** (serie più lunga e liquida, coerente col F&G); conversione in EUR solo per gli importi degli ordini (EUR/USD BCE o BTC-EUR dell'exchange). |
| 16 | **D** | Config, `carrello_min = 80 €` "anti-fee" | Con fee **proporzionali** (0,1% Binance/Kraken, 1,49% Revolut) aggregare non risparmia nulla: 3 ordini da 35 € costano esattamente come uno da 105 €. Serve solo contro fee fisse o minimi d'ordine (Binance ~5 €, Kraken ~10 €). Nel backtest l'aggregazione **costa** 0,5-1,3% di BTC (compra in media 10 giorni dopo, in un mercato che sale). | Tenerlo solo come "cadenza dell'umano" (quante volte al mese vuoi eseguire a mano) e dirlo chiaramente; il valore ottimo per i BTC è 0 (comprare ogni settimana). |
| 17 | **D** | Config, `soglia_attivazione = +15%` "perché le fee round-trip" | Motivazione sbagliata: un round-trip allo 0,1% costa 0,2%, non 15%. La soglia è comunque utile (evita vendite in rialzi tiepidi), ma la sua giustificazione vera è il rischio di whipsaw, non le fee. | Tenere la soglia, correggere il commento; con le soglie di euforia di §2.4 diventa ridondante. |
| 18 | **A** | Config, "nessun vincolo fiscale" | Assunzione da verificare per la tua residenza fiscale: se le plusvalenze crypto sono tassate, ogni vendi-e-ricompra cristallizza una plusvalenza e il break-even del SELL peggiora di molto. | Aggiungere un parametro `tax_rate` (0 se davvero non applicabile) e includerlo nel calcolo del "valore netto del SELL" nell'autopsia. Non sono un consulente fiscale: verifica con chi lo è. |
| 19 | **D** | Config, importi assoluti | 140/60/35/15/120/125/80/100 € sono tutti hard-coded su 200 €/mese. | Tutto in **frazioni di `budget_mese`** (70%/30%, riserva_max = 60%, tetto_singolo = 62,5%, carrello_min = 40%, carrello_sell_min = 50%…): passare a 500 o 1000 €/mese diventa un parametro. Gli unici assoluti veri sono i minimi d'ordine dell'exchange. |
| 20 | **A** | Persistenza 5 giorni | "rsi ≤ 30 da ≥ 5 giorni" su RSI giornaliero è un evento raro (nel 2018-2026 accade una manciata di volte); "rsi ≥ 75 da ≥ 5 giorni" idem. Va bene come *puntello* ma non come motore. | Specificare RSI-14 di Wilder su chiusure giornaliere; valutare in v6 l'RSI **settimanale** (vedi §4). |

---

## 3. Backtest su dati reali

### 3.1 Metodo
- **Motore**: implementazione fedele dello pseudo-codice (`backtest/backtest_v51.py`), con le sole modifiche necessarie a
  farlo girare (fix #5, #6, #7, #10, #12 sopra) e le interpretazioni dichiarate in testa al file (livelli esclusivi, banda
  della settimana precedente per la mutua esclusione, ecc.). Ogni interpretazione è un commento `I1…I11` nel codice.
- **Cadenza**: decisione ogni lunedì con gli indicatori del giorno; esecuzione alla chiusura del lunedì; fee 0,1% su ogni
  ordine, uguale per tutte le strategie. Tre atleti con **identici flussi di cassa** (200 $/mese): DCA puro (200 diviso sui
  lunedì del mese), v4 (solo BUY), v5.1 (BUY + SELL).
- **Metrica**: BTC-equivalente a fine periodo = BTC in portafoglio + cash residuo / prezzo finale. È la metrica del
  documento ("BTC per euro investito"). Il ROI in euro dipende dal prezzo finale e non distingue le strategie.
- **Valuta**: tutto in USD (serie Coinbase BTC-USD). Le differenze relative tra strategie sono le stesse che in EUR.
- **Audit**: per ogni run `depositi + ricavi_vendite − speso − cash = 0,00` (verificato).

### 3.2 Dati (verificati, non a memoria)
- **Prezzo**: Coinbase Exchange, candele giornaliere BTC-USD, 2017-01-01 → 2026-09-17 (3.547 giorni, nessun buco).
  Serie estratta a blocchi e validata con 120 candele ri-lette verbatim a campione (120/120 identiche) e con il controllo di
  continuità dei timestamp (ha scovato una riga saltata, 2021-02-07, poi corretta con la candela originale).
- **Fear & Greed**: alternative.me, 2018-02-01 → 2026-09-18 (3.148 giorni). Due buchi propri della fonte
  (2018-04-14/16, 2024-10-26), riempiti col valore precedente. Il 2021 è stato confrontato tra due copie indipendenti
  (2 differenze su 365 in una copia, risolte ri-leggendo i valori originali). Gli altri anni sono a passata singola: possibili
  errori isolati di ±1 giorno, irrilevanti con regole a "5 giorni consecutivi". **Il bot vero leggerà l'API direttamente**.
- **Indicatori**: SMA200 e max365 su chiusure; RSI-14 Wilder; streak giornalieri per le regole "da ≥5 giorni".
- I dati sono in `data/` e gli script in `backtest/` così il prossimo agente riparte da lì senza rifare tutto.

### 3.3 Risultati — BTC accumulati rispetto al DCA puro (fine: 14-09-2026, BTC = 78.175 $)

| Inizio | DCA puro (BTC) | v4 (solo BUY) | v5.1 (BUY+SELL) | n. vendite v5.1 |
|--------|---------------:|-------------:|----------------:|---------------:|
| 2018-02 | 1,28248 | −1,29% | **−14,02%** | 43 |
| 2019-01 | 0,94597 | −2,96% | **−15,73%** | 32 |
| 2020-01 | 0,56225 | −2,35% | **−10,13%** | 26 |
| 2021-01 | 0,32184 | −0,29% | +2,04% | 14 |
| 2022-01 | 0,26841 | −0,52% | +1,30% | 13 |
| 2023-01 | 0,17200 | −3,32% | −2,06% | 13 |
| 2024-01 | 0,08528 | +0,40% | +0,56% | 6 |
| 2025-01 | 0,04737 | +4,35% | +4,35% | 0 |

Traiettoria della finestra 2018→2026 (v5.1 vs DCA): +3,7% a fine 2018, **+9,8% a fine 2019** (il SELL di metà 2019 e il
rientro di fine 2019 funzionano), poi **−8,4% a fine 2020, −20,0% a fine 2021**, e da lì non recupera più (−14% oggi).

### 3.4 Autopsia dell'episodio 2020-21 (perché il SELL perde)
- 16-11-2020, prezzo 16.727 $, +55% sopra media200 (+30), F&G ≥ 80 da 11 giorni (+15), prezzo sul massimo a 365 giorni
  (+10) → euforia 55 → banda SELL 1; la settimana dopo (RSI ≥ 75 da 5 giorni) euforia 95 → banda 3 → vende il 30% del
  residuo a settimana: **19 vendite, 0,51 BTC su 1,00 in portafoglio, tra 16,7k e 55,7k** (prezzo medio ~22,5k), riserva
  = 11.401 $.
- Maggio-luglio 2021: prezzo 30-34k, banda stress 1 → il rientro è `min(riserva, 125 − DCA − dip)` ≈ 75-82 $/settimana →
  in sei settimane di banda 1 rientrano **~390 $ su 11.401**.
- 23-08-2021: scadenza dei 4 mesi → 11.011 $ diventano DCA → **ricomprati il 30-08-2021 a ~47k**.
- Risultato: venduto a ~22,5k, ricomprato a 47k su metà dello stack → −20% di BTC. Non è "il mercato ha fatto una cosa
  strana": è il meccanismo che, per costruzione, non può rientrare.

### 3.5 Diagnostica: quale correzione conta
Stessa finestra 2018→2026, varianti cumulative del modulo SELL:

| Variante | vs DCA (2018) | vs DCA (2019) | vs DCA (2020) | note |
|----------|---------:|---------:|---------:|------|
| v5.1 come da spec | −14,0% | −15,7% | −10,1% | |
| + rientro proporzionale alla riserva (#1) | −9,5% | −12,1% | −8,1% | |
| + nessuna scadenza (#2) | −4,1% | −8,3% | −8,8% | |
| + soglie euforia 1.5×/1.8×/2.2× media200 (#4) | **+5,1%** | **+2,2%** | +0,3% | 8 vendite; nelle finestre 2021+ non vende mai (= v4) |
| + bande a obiettivo cumulato (#3), con le soglie alte | +2,3% | −1,2% | −3,2% | vende di più al primo scatto (gen 2021) |

Lettura onesta: il +5% viene quasi interamente da **un episodio** (vendita 28-12-2020→01-03-2021 a 27-54k, riacquisto
giu 2021→lug 2022 a 20-39k). Il top di marzo 2024 con le soglie alte non viene venduto: euforia 75 il 4-3-2024 ma 10 la
settimana prima e 40 quella dopo, la doppia conferma non scatta (il picco a +82/+84% sopra media200 dura due settimane).
Due cicli non fanno una statistica: il modulo SELL è **plausibile ma non dimostrato**, e la versione scritta oggi è
**dimostratamente dannosa**.

### 3.6 Diagnostica lato BUY (perché v4 non batte il DCA)
Finestra 2018→2026, v4 con un parametro cambiato alla volta: `carrello_min = 0` (compra ogni settimana) → da −1,29% a
**0,00%**; `riserva_max = 60` → −0,55%; `riserva_max = 300` → −1,66%; `quota_dip = 15%` → −1,16%; senza F&G → −1,66%.
Cioè: l'aggregazione costa, la riserva costa (cash fermo in un mercato che nel periodo sale), il F&G aiuta un po'. I dip
comprati a sconto (2.337 $ su 20.649 in 8,6 anni: 13 settimane in banda 3, 9 in banda 2, 112 in banda 1) sono troppo
piccoli per compensare. Attenzione al **bias della data finale**: misurato sui minimi (dic 2018, mar 2020) v4 sembra
+4/+11% — ma è il cash valutato al prezzo di minimo, non BTC in più; quando il prezzo risale il vantaggio svanisce.

---

## 4. Gli "occhi": gli indicatori bastano?

Per una strategia a cadenza settimanale su orizzonte di cicli, **media200 / drawdown dal massimo 365 / RSI-14 / F&G è un
set minimo ragionevole** e ha il pregio di essere calcolabile da una sola serie di prezzi più un'API gratuita. Il F&G è di
suo un composito (volatilità, momentum, social, dominance) e in parte duplica l'RSI: come "puntello" va bene.

Aggiunte a costo zero (stessa serie di prezzi) che vale la pena testare in v6 — **una alla volta, misurando**:
1. **Media mobile a 200 settimane (200-WMA)**: citata di solito come "pavimento" dei bear market di BTC. Sui nostri dati
   (calcolabile dal 2020 in poi): giugno 2022 −8% sotto, **novembre 2022 −34% sotto** (quindi non è un pavimento
   garantito), giugno 2026 a contatto (+2%). Utile come definizione di "zona di accumulo estremo" (prezzo < 200-WMA), non
   come livello magico. I dati pre-2017 per verificarla su 2015/2018 vanno scaricati (Bitstamp/Coinbase dal 2015).
2. **RSI-14 settimanale** invece di "RSI giornaliero ≥75 per 5 giorni". Dati alla mano: ≥ 85 solo nelle fasi paraboliche
   (dic 2017: 95; gen-feb 2021: 94; mar 2024: 85), mentre i top "lenti" non lo raggiungono (nov 2021: 68; gen 2025: 65);
   minimi di ciclo a 29-31 (dic 2018, mar 2020, nov 2022, feb 2026). Cioè: ottimo per i blow-off top, cieco sui top a
   doppio massimo. Coerente con la cadenza settimanale del bot.
3. **Mayer Multiple** (prezzo/media200) come variabile principale dell'euforia con soglie 1.5/1.8/2.2 — è la stessa cosa di
   `cheapness` ma ragionata in multipli: è già quello che rende positivo il SELL nel backtest.
4. **Pi Cycle Top** (111-DMA che incrocia 2×350-DMA): indicatore popolare per i top 2013/2017/2021 (da verificare sui
   nostri dati nel backtest, non l'ho testato). Al massimo come +punti di euforia, mai da solo.

Cose da **non** aggiungere in v1: on-chain (MVRV, realized price — le fonti gratuite sono instabili), funding rate (utile ma
richiede un'altra API), volumi, macro. Più indicatori con due cicli di storia = più overfitting, non più alpha.

> **CORREZIONE (2026-09-20, sessione 03).** La frase qui sopra — "on-chain (MVRV, realized price): le fonti gratuite sono
> instabili" — **era sbagliata**. Verificato con chiamate reali: la **CoinMetrics Community API** serve `CapMVRVCur` e
> `CapMrktCurUSD` per BTC, giornalieri, **dal 2010-07-18**, gratis e senza chiave (dettagli e limiti in
> `docs/02_indicatori_bot_report.md` §1). Resta vero che `CapRealUSD` (realized cap) è a pagamento — risponde 403 — ma la
> realized cap si ricava per divisione (market cap / MVRV). Il Pi Cycle Top del punto 4 è stato testato: vedi
> `02_indicatori_bot_report.md` §4, spara raramente e negli ultimi due massimi non ha sparato affatto.

---

## 5. Fonti dati (tutte gratuite, senza account, senza scraping)

Verificate oggi con chiamate reali:
- **alternative.me** — `https://api.alternative.me/fng/?limit=0&format=json` → tutta la storia F&G dal 2018-02-01, JSON, nessuna chiave. Aggiornamento ~00:00 UTC.
- **Coinbase Exchange** — `https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400&start=…&end=…` → candele giornaliere (max 300 per chiamata), storia dal 2015, nessuna chiave. Esiste anche `BTC-EUR`.
- **Binance** — `https://api.binance.com/api/v3/klines?symbol=BTCEUR&interval=1d&limit=1000` → pubblica, nessuna chiave; storico completo via `data.binance.vision` (CSV mensili). Non testata dal sandbox (dominio bloccato qui, non dal tuo VPS).
- **Kraken** — `https://api.kraken.com/0/public/OHLC?pair=XBTEUR&interval=1440` (limite documentato ~720 candele: ok per il live, non per il backtest; non testata dal sandbox).
- **CoinMetrics Community** (aggiunta il 2026-09-20, sessione 03) — `https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur,CapMrktCurUSD,PriceUSD&frequency=1d&start_time=…&end_time=…` → MVRV, market cap e prezzo di riferimento giornalieri dal 2010-07-18, nessuna chiave. Dato del giorno T disponibile dal giorno T+1 (nessun valore intraday). `CapRealUSD` è a pagamento (403).

Quindi: **niente TradingView**. Lo scraping della pagina è fragile, contro i loro termini, e non serve: tutto ciò che il
bot "vede" (prezzo, media200, max365, RSI, F&G) si calcola da una serie di chiusure giornaliere + F&G. Regola per il
progetto: fetcher con **due fonti** (primaria + fallback) e cache locale in SQLite; se entrambe falliscono il bot lo dice su
Telegram e non decide.

---

## 6. Obiettivo e metrica: "aumentare il ROI, anche mensile"

Il documento ha già la metrica giusta: **BTC per euro investito** (vs DCA puro). Il ROI mensile in euro è rumore: con 200
€/mese e BTC che fa ±30% in un mese, il ritorno del mese è deciso dal prezzo, non dal bot. Il bot può migliorare **solo il
prezzo medio di carico**, e il backtest dice quanto: pochi punti percentuali su anni, in positivo o in negativo.

Aspettative realistiche per la v6: BUY ≈ DCA (obiettivo: non perdere nulla per attriti), SELL sperimentale con potenziale
+0/+5% per ciclo e rischio di whipsaw. Il valore certo del bot è **comportamentale**: fa comprare ogni settimana, in
downtrend compreso, senza decisioni emotive, e tiene i conti.

---

## 7. Scalare da 200 a 500/1000 €/mese

Nessun problema concettuale se (#19) tutto è espresso in frazioni di `budget_mese`. Da tenere presente:
- i minimi d'ordine spariscono come vincolo già a 200 €; `carrello_min` diventa puramente "quante volte al mese esegui a mano";
- la `riserva_sell` cresce con lo stack, non col budget: **è il motivo per cui il rientro va reso proporzionale (#1)**;
- il `tetto_singolo` come protezione da "ordine gigante per bug" ha senso, ma in **multipli del budget settimanale**, non in euro.

---

## 8. Cosa cambiare prima di scrivere il piano (proposta v6)

1. Correggere i bug B (#5, #6, #7, #12, #13) e chiudere le ambiguità A (#8, #9, #10, #11, #14, #15, #20) **nel documento di
   specifica**, prima del codice. La spec deve essere eseguibile senza interpretazioni.
2. Lato BUY: `carrello_min` come parametro di comodità (default = 1 ordine/settimana o 1 ogni 2), non come "anti-fee".
   Valutare `riserva_max` più bassa. Tutto in frazioni di `budget_mese`.
3. Lato SELL: **spento di default** (`sell_enabled = false`), riscritto con #1, #2, #3, #4; acceso solo dopo backtest esteso
   (walk-forward per start-date e per end-date, come in §3.3/3.5) e comunque con la regola di autopsia già prevista.
4. Architettura: **un solo motore puro** `decidi(stato, dati_del_giorno) → (decisioni, nuovo_stato)`, usato identico dal
   backtester e dal bot live. È l'unico modo per avere "atleta_v4" e "atleta_DCA" davvero comparabili e per non avere due
   logiche che divergono. Contabilità a libro mastro (SQLite), audit sul mastro.
5. Telegram: comandi `/stato`, `/fatto <eur> <btc>`, `/annulla`, `/deposito <eur>`, `/pausa`, `/riprendi`, `/config`,
   `/storico`, `/audit`, `/simula` (cosa farebbe oggi). Notifiche: ordine, promemoria pendente, report settimanale, alert
   dati mancanti.
6. Data layer: fetcher primario + fallback, cache SQLite, controlli di sanità (buchi, salti >30%, timestamp).
7. Primo deliverable del piano: **backtester + spec v6 chiusa**, non il bot Telegram. Il bot è la parte facile (hai già
   fatto bot Telegram); la parte difficile è decidere cosa deve dire.

---

## 9. Decisioni che servono da te (bloccano il piano)

1. **Exchange e fee reali**: Binance/Kraken (~0,1%) o app tipo Revolut (~1,5% + spread)? Con l'1,5% il round-trip del SELL
   costa >3% e l'aggregazione degli ordini ha un senso in più (solo se ci sono fee fisse).
2. **Fiscalità**: le plusvalenze sono davvero irrilevanti nella tua residenza? Se no, `tax_rate` entra nel SELL.
3. **Valuta di riferimento degli ordini**: EUR (probabile). Gli indicatori resterebbero su BTC-USD.
4. **SELL in v6**: spento di default e sperimentale (mia raccomandazione), oppure vuoi che sia comunque nel primo rilascio?
5. **Hosting**: il tuo VPS Ubuntu (cron/systemd + SQLite) o il Raspberry? Entrambi vanno bene; cambia solo il deploy.
6. **Orizzonte di valutazione**: 12 mesi di paper-trading prima di mettere soldi sul SELL? (Il BUY può partire subito.)

---

## Appendice A — Interpretazioni usate nel backtest (copiate dal codice)
I1 livelli stress/euforia esclusivi, `base` ignorata · I2 decisione il lunedì, esecuzione alla chiusura del lunedì, fee 0,1% ·
I3 trend con streak ≥5 giorni sopra/sotto media200 · I4 mutua esclusione con la banda stress della settimana precedente ·
I5 DCA settimanale = budget_DCA_rimasto / lunedì rimanenti · I6 dip banda 3 = min(37, 15 + 0,4·riserva_dip) · I7 banda 0:
15 € spostati (non copiati) in riserva_dip · I8 cap 50% su (stack + venduti nel ciclo), reset a riserva_sell = 0 e banda 0 ·
I9 carrello_sell svuotato a banda 0 · I10 riserva_sell scaduta → budget_DCA del mese corrente · I11 F&G mancanti = valore precedente.

## Appendice B — File prodotti in questa sessione
- `docs/01_analisi_pseudocodice_v5.1.md` (questo documento)
- `docs/tracking/2026-09-19_sessione-01.md` (log di sessione)
- `backtest/backtest_v51.py` — motore v5.1/v4/DCA + report (eseguire: `python3 backtest_v51.py`)
- `backtest/variants_sell.py` — varianti diagnostiche del SELL (§3.5)
- `data/btc_close_usd_coinbase.csv` — chiusure giornaliere 2017-01-01 → 2026-09-17
- `data/fng_alternative_me.csv` — Fear & Greed 2018-02-01 → 2026-09-18
