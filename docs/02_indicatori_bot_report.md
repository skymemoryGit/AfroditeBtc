# Indicatori del bot di report — validazione MVRV, RSI settimanale, 200-WMA, Pi Cycle

Sessione 03 — 2026-09-20. Compito assegnato nella sessione 02: chiudere la validazione MVRV (limiti della fonte,
profondità storica, ritardo, grezzo vs Z-score) e testare i nuovi indicatori sui dati reali.

**Metodo**: tutte le affermazioni qui sotto vengono da chiamate HTTP vere fatte oggi e da calcoli su
`data/coinmetrics_btc_mvrv.csv`, riproducibili con `python3 backtest/validate_mvrv.py`
(output salvato in `backtest/validate_mvrv_output.txt`). Nessun numero è preso a memoria.
Le implementazioni degli indicatori sono state ricontrollate contro `pandas`/`numpy` (§7).

---

## 0. Verdetto in breve

1. **La fonte MVRV gratuita esiste e regge**: CoinMetrics Community, dal **2010-07-18**, senza chiave, senza scraping,
   dato del giorno T disponibile il giorno T+1. L'assunzione contraria nell'analisi v5.1 (§4) è corretta nel documento.
2. **Usare l'MVRV grezzo + il percentile a 4 anni. NON usare lo Z-score classico** come soglia: i suoi valori ai massimi
   di ciclo crollano di ciclo in ciclo (10,7 → 9,4 → 5,4 → 3,5 → 2,5). Chi oggi aspetta "Z > 7 per vendere" aspetta un
   numero che non tornerà. Dettaglio e numeri in §2.
3. **MVRV non è un doppione del Mayer multiple**, anche se ci somiglia (r = 0,85): a parità di Mayer, i giorni con MVRV
   sotto la mediana hanno reso molto di più a 12 mesi (§3). Vale la pena tenerlo nel report.
4. **Pi Cycle Top: da tenere solo come curiosità.** Negli ultimi due massimi (2021-11 e 2025-10) **non ha sparato**, e
   nel ciclo attuale non si è mai avvicinato (massimo 0,736 su una soglia di 1,00) (§4).
5. **200-WMA e RSI settimanale: confermati utili come contesto**, con l'avvertenza che la 200-WMA non è un pavimento
   (nel 2022 il prezzo ci è stato 177 giorni sotto, fino a −34%) (§5-6).

---

## 1. La fonte MVRV — validazione completa

Endpoint (nessuna API key, nessun account):

```
https://community-api.coinmetrics.io/v4/timeseries/asset-metrics
   ?assets=btc&metrics=CapMVRVCur,CapMrktCurUSD,PriceUSD&frequency=1d
   &start_time=2010-07-01&end_time=2026-09-19&page_size=10000
```

| Domanda della sessione 02 | Risposta verificata oggi |
|---|---|
| Fino a quando risale la storia? | **2010-07-18**, sia da catalogo (`/catalog-v2/asset-metrics`, campo `min_time`) sia scaricando davvero la serie: 5.908 giorni, **zero buchi** fino al 2026-09-19. |
| Serve una chiave? | No. `"community": true` nel catalogo per `CapMVRVCur`, `CapMrktCurUSD`, `PriceUSD`. |
| Rate limit? | Documentato: **10 richieste ogni 6 secondi per IP**, 10 richieste parallele, `page_size` max 10.000. Misurato oggi: **20 richieste in 3,9 s, zero errori, zero 429**. Il bot ne farà 1-2 al giorno: irrilevante. |
| C'è ritardo sui giorni recenti? | Sì, **un giorno**. Alle **08:31 UTC del 2026-09-20** l'ultimo dato disponibile era **2026-09-19** (`max_time` del catalogo = ultimo punto della serie). Nessun valore intraday: la frequenza disponibile è solo `1d`. Per un report giornaliero mandato la mattina significa lavorare sull'MVRV di **ieri** — va scritto nel messaggio, non nascosto. |
| I dati passati vengono rivisti? | Nei campioni controllati **no**. Le finestre 2018-01-01→10 e 2024-01-01→10 lette oggi dall'API sono **identiche** a quelle salvate nel CSV, e 9 date sparse (2013, 2015, 2017, 2018, 2021, 2022, 2024, 2025, 2026) ri-lette una per una coincidono **cifra per cifra** con il file. Non è una garanzia sul futuro: la verifica va ripetuta quando il bot sarà in esercizio. |
| Conviene prendere anche `CapRealUSD`? | **Non si può**: nel tier community `CapRealUSD` non è nel catalogo e la chiamata risponde **403**. Ma non serve: `realized cap = CapMrktCurUSD / CapMVRVCur`. Oggi (2026-09-19): market cap 1.632.287.115.291 $, realized cap ricavata 1.069.885.926.397 $. |

Due note sulla sessione 02, per chi rilegge:

- I valori annotati là ("2018-01-01→2018-01-10: 2,69→3,26" e "2024: ~1,94→2,11") **non sono** primo e ultimo giorno
  della finestra. La serie reale è: 2018-01-01 = 2,6942 … 2018-01-05 = **3,2620** (massimo della finestra) … 2018-01-10 = 2,7333;
  2024-01-01 = 2,0050 … 2024-01-03 = **1,9416** (minimo) … 2024-01-08 = **2,1052** … 2024-01-10 = 2,0904.
  Quei numeri esistono tutti dentro le finestre, ma erano accoppiati alle date sbagliate. Il dato è buono, l'annotazione no.
- Controllo incrociato indipendente: il `PriceUSD` di CoinMetrics confrontato con le chiusure Coinbase già in
  `data/btc_close_usd_coinbase.csv` su **3.547 giorni** dà uno scarto **medio dello 0,18 %** e **massimo del 5,2 %**
  (giorni di forte volatilità: sono due cose diverse — chiusura di un singolo exchange contro prezzo di riferimento
  ponderato su più exchange). Per i calcoli del bot va usata **una sola** delle due serie, non un misto.

**File scaricato**: `data/coinmetrics_btc_mvrv.csv` — colonne `date,mvrv,market_cap_usd,price_usd`,
2010-07-18 → 2026-09-19, 5.908 righe.

---

## 2. MVRV grezzo, Z-score o percentile? — decisione con i numeri

MVRV Z-score = (market cap − realized cap) / deviazione standard della market cap, con deviazione calcolata su finestra
**espansiva** (tutta la storia fino a oggi), che è la definizione delle dashboard pubbliche.

Valore di ogni variante ai massimi e ai minimi di ciclo (massimi e minimi **trovati dai dati**, non inseriti a mano):

| data | tipo | MVRV | Z espansivo | Z 4 anni | percentile 4 anni | Mayer |
|---|---|---|---|---|---|---|
| 2013-04-09 | TOP | 5,64 | 10,66 | n/d | n/d | 8,26 |
| 2013-12-04 | TOP | 4,72 | 7,71 | n/d | n/d | 5,71 |
| 2017-12-16 | TOP | 4,43 | 9,36 | 3,70 | 99,9 | 3,78 |
| 2021-04-13 | TOP | 3,43 | 5,38 | 1,93 | 95,8 | 1,97 |
| 2021-11-08 | TOP | 2,85 | 3,53 | 1,41 | 88,3 | 1,48 |
| 2025-10-06 | TOP* | 2,29 | 2,53 | 0,99 | 83,6 | 1,18 |
| 2015-01-14 | BOTTOM | 0,56 | −0,60 | −1,26 | 2,6 | 0,40 |
| 2018-12-15 | BOTTOM | 0,69 | −0,49 | −1,33 | 0,4 | 0,51 |
| 2022-11-09 | BOTTOM | 0,75 | −0,36 | −1,45 | 0,7 | 0,67 |

\* 2025-10-06 è il **massimo assoluto finora** (124.824 $), non un massimo di ciclo confermato: da lì il prezzo è
−34,9 % (oggi 81.262 $). Lo tratto come massimo perché sono passati oltre 11 mesi, ma è un'assunzione, non un fatto.

Stabilità della soglia sui 4 massimi dell'era moderna (coefficiente di variazione: **più basso = soglia che si ripete**):

| indicatore | valori ai 4 massimi | CV |
|---|---|---|
| **percentile MVRV su 4 anni** | 99,9 · 95,8 · 88,3 · 83,6 | **0,069** |
| MVRV grezzo | 4,43 · 3,43 · 2,85 · 2,29 | 0,244 |
| Mayer multiple | 3,78 · 1,97 · 1,48 · 1,18 | 0,479 |
| Z-score espansivo | 9,36 · 5,38 · 3,53 · 2,53 | 0,502 |
| Z-score 4 anni rolling | 3,70 · 1,93 · 1,41 · 0,99 | 0,514 |

Perché lo Z-score classico peggiora: il denominatore è la deviazione standard di **tutta** la storia della market cap,
che cresce a ogni ciclo; il numeratore cresce meno. Risultato: la stessa "euforia" produce numeri sempre più piccoli.
È una proprietà della formula, non del mercato — quindi **le soglie da manuale (Z > 7 = vendere, Z < 0 = comprare) sono
oggi tarate su un mondo che non c'è più**. Sul lato basso invece regge ancora (Z < 0 ha coinciso con tutti e tre i minimi).

Rendimento a **+365 giorni** per banda di MVRV, **solo dal 2017** (i giorni prima del 2017 hanno numeri assurdi, +3.800 %,
che gonfierebbero ogni media):

| banda MVRV | giorni | mediana +1 anno | % positivi | peggiore | migliore |
|---|---|---|---|---|---|
| < 1 | 319 | **+92 %** | **100 %** | +13 % | +1.064 % |
| 1 – 1,5 | 712 | +90 % | 91 % | −56 % | +989 % |
| 1,5 – 2 | 910 | +32 % | 60 % | −66 % | +1.621 % |
| 2 – 2,5 | 736 | −5 % | 48 % | −73 % | +1.816 % |
| 2,5 – 3,5 | 458 | +11 % | 56 % | −78 % | +1.228 % |
| > 3,5 | 49 | **−31 %** | 18 % | −84 % | +172 % |

Stessa cosa con il percentile a 4 anni (dal 2017): pct 0-10 → mediana **+127 %**, 100 % positivi, peggior caso **+13 %**;
pct 10-25 → +83 %; pct 25-50 → +88 %; pct 50-75 → +13 %; pct 75-90 → +2 %; pct 90-100 → +9 % (55 % positivi, peggior caso −84 %).

**Lettura onesta**: il lato "economico" funziona in entrambe le versioni ed è quello che serve a te (compri ogni mese,
non vendi). Il lato "caro" è molto più debole: sopra il 75° percentile la mediana si azzera ma non diventa negativa,
perché nei mercati toro si sta "caro" per mesi mentre il prezzo continua a salire. L'unica banda con mediana
chiaramente negativa è MVRV > 3,5, che **dal 2017 esiste solo per 49 giorni** e che ai ritmi attuali potrebbe non
tornare mai più.

**Decisione**: nel bot di report si mostrano **MVRV grezzo** (soglie assolute, con il limite qui sopra dichiarato) e
**percentile MVRV su 4 anni** (la variante che si mantiene confrontabile tra cicli). Lo Z-score espansivo si può
calcolare e mostrare come riga di contesto, **mai** come soglia di decisione: il codice lo calcola già
(`indicators.mvrv_zscore_expanding`), quindi la scelta resta reversibile senza rifare nulla.

---

## 3. MVRV aggiunge qualcosa rispetto al Mayer multiple?

Domanda legittima: MVRV e Mayer sono correlati (**r = 0,85** dal 2017, r = 0,83 su tutta la storia) e il set del report
ha già il Mayer. Test: dentro ogni banda di Mayer, divido i giorni tra MVRV sotto e sopra la mediana di quella banda
e guardo il rendimento a 12 mesi (dal 2017).

| banda Mayer | giorni | MVRV mediano | +1 anno con MVRV basso | +1 anno con MVRV alto |
|---|---|---|---|---|
| 0 – 0,8 | 523 | 1,05 | **+88 %** | +13 % |
| 0,8 – 1,0 | 680 | 1,54 | **+73 %** | −26 % |
| 1,0 – 1,2 | 677 | 1,80 | **+166 %** | −30 % |
| 1,2 – 1,5 | 707 | 2,06 | **+130 %** | +2 % |
| 1,5 – 2,4 | 538 | 2,73 | +25 % | +13 % |

A parità di Mayer, l'MVRV separa ancora. Motivo economico plausibile: il Mayer guarda solo il prezzo degli ultimi 200
giorni, l'MVRV guarda **a che prezzo si sono mossi davvero i bitcoin** (realized cap), che si aggiorna anche quando il
prezzo sta fermo. Non sono la stessa informazione. **MVRV resta nel set.**

Nota d'uso: MVRV e Mayer non si accendono insieme. Dal 2017, "zona economica" per entrambi (MVRV < 1 *e* Mayer < 0,8):
251 giorni; solo MVRV < 1: 68 giorni; solo Mayer < 0,8: 359 giorni. Nel report vanno mostrati separati, non fusi in un
unico punteggio che nasconde il disaccordo.

---

## 4. Pi Cycle Top — testato (mai fatto prima)

Definizione: segnale quando la media a 111 giorni incrocia **sopra** il doppio della media a 350 giorni.

Incroci trovati su tutta la serie 2010-2026 — **quattro, tutti prima del 2022**:

| data del segnale | prezzo | massimo di ciclo vicino |
|---|---|---|
| 2013-04-06 | 143 $ | 2013-04-09 (3 giorni dopo, 231 $) |
| 2013-12-05 | 1.027 $ | 2013-12-04 (il giorno **prima**: segnale in ritardo di 1 giorno) |
| 2017-12-16 | 19.641 $ | 2017-12-16 (lo stesso giorno) |
| 2021-04-12 | 59.906 $ | 2021-04-13 (il giorno dopo, 63.446 $) |

Quando ha sparato è stato **notevolmente puntuale**. Il problema è quando non spara:

- massimo del rapporto 2018-07 → 2021-12: **1,004** (2021-04-17) — ha sparato appena appena;
- massimo del rapporto 2022-01 → oggi: **0,736** (2024-06-01) — **mai vicino al segnale**;
- oggi (2026-09-19) il rapporto è **0,43**.

Sui massimi del 2021-11 e del 2025-10 il Pi Cycle **non ha detto niente**. Con cicli sempre meno esplosivi, la soglia
"111-DMA = 2 × 350-DMA" chiede un'accelerazione che il mercato non fa più. **Verdetto**: si calcola (costa nulla, stessa
serie di prezzi) e si mostra il rapporto come riga di contesto ("quanto manca al segnale"), ma **non** va usato come
allarme principale né dato per buono: negli ultimi 5 anni sarebbe stato muto.

---

## 5. 200-WMA (media a 200 settimane)

- Disponibile dal 2014 in poi: **4.521 giorni** con la media calcolabile.
- Il prezzo ci è stato **sotto 387 giorni, cioè l'8,6 % del tempo**.
- Massimo sfondamento: **−34 % il 2022-11-21**.
- Anni con prezzo sotto la 200-WMA: 2015 (31 gg, fino a −9 %), 2020 (6 gg, −10 %), **2022 (177 gg, −34 %)**,
  **2023 (145 gg, −32 %)**, **2026 (27 gg, −7 %)**.

Due conseguenze per il testo del report: (a) "sotto la 200-WMA" è un evento raro e storicamente un'ottima zona di
accumulo; (b) **non è un pavimento** — nel 2022-23 ci si è stati sotto per quasi un anno di calendario. Il messaggio
del bot deve dire entrambe le cose, altrimenti invita a comprare "tutto adesso" su un livello che può essere bucato
di un terzo. Oggi il prezzo è **1,24 volte** la 200-WMA (**65.487 $** la media al 2026-09-19 contando la settimana in corso, 81.262 $ il prezzo; la stessa media calcolata sull'ultima settimana **chiusa** è 65.162,24 $ — è il valore usato nel confronto con pandas in §7).

---

## 6. RSI settimanale (nuovo) e RSI giornaliero

Implementazione: RSI di Wilder su chiusure settimanali ISO (lunedì-domenica), con la settimana in corso ricalcolata
ogni giorno usando il prezzo di oggi come chiusura provvisoria — cioè quello che si vede sul grafico settimanale in
diretta. Chi preferisce solo settimane chiuse ha già il parametro (`include_current_week=False`).

RSI-14 settimanale ai massimi: **90,4** (2017-12-16), **74,2** (2021-04-13), **70,2** (2021-11-08), **65,2** (2025-10-06).
Ai minimi: **25,8** (2015-01-14), **29,0** (2018-12-15), **30,6** (2022-11-09).

Anche qui la soglia alta si abbassa di ciclo in ciclo (come il Mayer e come l'MVRV): "RSI settimanale > 80 = top" è una
regola del 2017. La soglia bassa invece è stabile: **sotto 30 sul settimanale = i tre minimi maggiori**. Nel report
conviene dire dove sta l'RSI settimanale **rispetto ai valori dei cicli passati**, non rispetto ai classici 30/70.

Oggi: RSI-14 giornaliero **64,3**, settimanale **58,8**.

---

## 7. Come sono stati controllati i calcoli

Ogni indicatore scritto a mano in `botbtc/indicators.py` (solo libreria standard, come il resto del progetto) è stato
ricalcolato con `pandas`/`numpy` e confrontato riga per riga. **Le librerie non entrano nel progetto**, servivano solo
come secondo parere:

| indicatore | esito del confronto |
|---|---|
| RSI-14 giornaliero | 5.894 valori, scarto massimo **0,0** |
| SMA 200 | scarto massimo 1,4 × 10⁻¹⁰ (arrotondamento) |
| Pi Cycle (rapporto e incroci) | scarto 3 × 10⁻¹⁵; **stesse 4 date** di incrocio |
| Drawdown da massimo 365 gg | scarto massimo 0,0 |
| Chiusure settimanali (845 settimane) | **identiche** |
| RSI-14 settimanale | identico sull'ultima settimana chiusa (54,54) |
| 200-WMA (ultima settimana chiusa) | identica (65.162,24) |
| MVRV Z-score espansivo | scarto massimo 7 × 10⁻¹⁵ |

Inoltre: continuità della serie MVRV verificata (0 buchi su 5.908 giorni), nessun valore vuoto, 9 date ri-lette
dall'API una per una e identiche al file.

**Limiti da tenere presenti** (valgono per tutti i numeri di questo documento):

1. I "giorni" nelle tabelle dei rendimenti **non sono osservazioni indipendenti**: finestre di 365 giorni che si
   sovrappongono. In termini di cicli veri abbiamo **3-4 osservazioni**, non 700. Nessuna di queste tabelle è una prova
   statistica; sono descrizioni di quello che è successo.
2. Tutto è calcolato **sulla storia di un solo asset** che è salito moltissimo nel periodo: qualunque banda "compra"
   sembra funzionare.
3. Le soglie assolute degenerano di ciclo in ciclo (dimostrato in §2 per MVRV, Z, Mayer, RSI-W): un bot che le usa
   fisse invecchia male. Il percentile è la contromisura, ma ha il difetto opposto (a inizio toro segna subito 100).
4. Per gli indicatori è stata usata la serie prezzi **CoinMetrics** (dal 2010), mentre il backtest v5.1 usa le chiusure
   **Coinbase** (dal 2017). Scarto medio 0,18 %, ma i due file non vanno mescolati dentro lo stesso calcolo.

---

## 7-bis. Fotografia del 2026-09-19 (ultimo giorno con tutti i dati)

| indicatore | valore | lettura |
|---|---|---|
| prezzo (CoinMetrics `PriceUSD`) | 81.262 $ | |
| MVRV grezzo | **1,526** | banda 1,5-2 = zona neutra |
| percentile MVRV 4 anni | **43,0** | (2 anni: 32,2) più economico della mediana degli ultimi 4 anni |
| Z-score espansivo (solo contesto) | 0,92 | |
| Mayer multiple | 1,15 | poco sopra la media a 200 giorni |
| drawdown dal massimo 365 gg | −34,9 % | massimo del periodo: 124.824 $ del 2025-10-06 |
| RSI-14 giornaliero / settimanale | 64,3 / 58,8 | nessun estremo |
| prezzo / 200-WMA | 1,24 | sopra, ma nel 2026 ci sono già stati 25 giorni sotto |
| Pi Cycle (rapporto, segnale a 1,00) | 0,43 | lontanissimo dal segnale |

Non è un consiglio: è la riga di stato che il bot di report dovrà saper scrivere da solo.

---

## 8. File prodotti in questa sessione

- `data/coinmetrics_btc_mvrv.csv` — MVRV, market cap, prezzo giornalieri 2010-07-18 → 2026-09-19 (5.908 righe).
- `botbtc/indicators.py` — libreria degli indicatori del bot di report: SMA200/Mayer, drawdown 365, RSI-14
  giornaliero e settimanale, 200-WMA, Pi Cycle, MVRV (grezzo, realized cap ricavata, Z-score espansivo, Z rolling,
  percentile). Nessuna dipendenza esterna, nessun lookahead.
- `backtest/validate_mvrv.py` — riproduce tutti i numeri di questo documento.
- `backtest/validate_mvrv_output.txt` — output della corsa di oggi.
- `docs/01_analisi_pseudocodice_v5.1.md` — corretta l'assunzione sbagliata su MVRV (§4) e aggiunta la fonte (§5).

## 9. Cosa manca (per la prossima sessione)

1. **Scrivere la struttura del report giornaliero**: quali righe, in che ordine, con quale testo per ogni banda —
   usando MVRV grezzo + percentile, Mayer, drawdown 365, RSI giornaliero e settimanale, 200-WMA, F&G, Pi Cycle come
   contesto. Le bande di "cheapness" corrette nell'analisi v5.1 §2 restano la base.
2. **Confronto storico automatico** (feature decisa in sessione 02): "l'ultima volta che eri in questa situazione era
   il …, e dopo 6/12 mesi BTC ha fatto …". I dati per farlo ci sono tutti ora, incluso l'MVRV.
3. **Fetcher con fallback e cache** per le tre fonti (Coinbase/Binance per il prezzo, alternative.me per F&G,
   CoinMetrics per MVRV), con la regola già fissata: se una fonte manca, il bot lo **dice** e non inventa.
4. Ricontrollare il ritardo di CoinMetrics quando il bot sarà attivo: se un giorno il dato T−1 non c'è ancora
   all'orario del report, il messaggio deve dirlo invece di mostrare un valore vecchio come se fosse di ieri.
