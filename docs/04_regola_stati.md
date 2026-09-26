# La regola dei tre stati — parametri, test, risultati

Sessione 07 · 2026-09-20 · Fase F2 del piano (`docs/03_piano_sviluppo.md`).

> **Ordine di scrittura di questo documento.** Il §1 (parametri) è stato scritto e salvato **prima** di far girare
> il test storico, come impone la regola procedurale della F2.3: i parametri si scelgono dai principi e dai numeri di
> `docs/02`, non dalle date che vogliamo veder accendere. I §3 e seguenti sono stati aggiunti dopo, con i risultati.
> Ogni ri-taratura fatta *dopo* aver visto l'esito è contata nel §6.

---

## 1. Parametri fissati prima del test

### 1.1 Ingredienti e orientamento

Sette ingredienti, tutti già validati in `docs/02`. Ognuno è orientato in modo che **valore alto = mercato caro**:

| ingrediente | orientamento | gruppo |
|---|---|---|
| prezzo / 200-WMA | alto = caro | nucleo di prezzo |
| Mayer multiple (prezzo / SMA200) | alto = caro | nucleo di prezzo |
| drawdown dal massimo a 365 giorni | alto (vicino a 0) = caro | nucleo di prezzo |
| RSI-14 settimanale | alto = caro | nucleo di prezzo |
| RSI-14 giornaliero | alto = caro | nucleo di prezzo |
| MVRV | alto = caro | arricchimento |
| Fear & Greed | alto = caro | arricchimento |

Il Pi Cycle **non entra nel punteggio** (D10: negli ultimi due massimi è rimasto muto): resta riga di contesto.

### 1.2 Da valore assoluto a profondità: rampa a percentile

Le soglie assolute invecchiano di ciclo in ciclo — è dimostrato in `docs/02` §2 per MVRV (4,43 → 2,29 ai massimi),
Mayer (3,78 → 1,18), RSI settimanale (90,2 → 65,1; dopo la correzione D41: 90,4 → 65,2) e Z-score (9,36 → 2,53). Quindi ogni ingrediente viene convertito
nel suo **percentile sulla finestra mobile di 4 anni** (1.460 giorni, la scelta di `docs/02` §2), calcolato senza
lookahead, e da lì in un punteggio di profondità:

```
economico_i = max(0, (30 - percentile_i) / 30)        # contribuisce solo sotto il 30° percentile
caro_i      = max(0, (percentile_i - 70) / 30)        # contribuisce solo sopra il 70° percentile
```

Entrambi valgono 0 in zona neutra e 1 all'estremo (percentile 0 o 100). La scelta di 30/70 è la stessa idea delle
bande di `docs/02` §2, dove il primo quartile di MVRV concentra i rendimenti migliori (decile più basso: mediana
+127 % a 12 mesi, 100 % di casi positivi) e l'ultimo quarto quelli peggiori.

### 1.3 Pesi

| ingrediente | peso | perché |
|---|---|---|
| prezzo / 200-WMA | **0,25** | è il caso che ha fatto nascere il progetto; da solo deve poter accendere lo stato (richiesta esplicita di F2.2-bis) |
| Mayer multiple | 0,20 | stessa famiglia, orizzonte più corto |
| drawdown 365 giorni | 0,20 | misura la distanza dal massimo recente, che le medie non colgono |
| RSI-14 settimanale | 0,10 | stabile sul lato basso (25,8 / 29,0 / 30,6 ai tre minimi), inaffidabile su quello alto |
| RSI-14 giornaliero | 0,05 | rumoroso su un orizzonte di mesi |
| **MVRV** | **0,30** | il peso singolo più alto: è l'unico con evidenza forte a 12 mesi e non è un doppione del Mayer (D9) |
| Fear & Greed | 0,10 | sentiment, molto correlato al prezzo: conferma, non decide |

Somma con tutti gli ingredienti: 1,20. Nucleo di solo prezzo: 0,80.

### 1.4 Degrado con grazia (F2.6)

Il punteggio è **normalizzato sui pesi effettivamente disponibili**:

```
punteggio = somma(peso_i * profondità_i) / somma(peso_i disponibili)
```

Se MVRV o Fear & Greed mancano, il punteggio resta sulla stessa scala 0-1 e il bot parla lo stesso, dichiarando con
quali ingredienti ha deciso. Si richiede però che **il nucleo di prezzo sia presente**: se mancano i prezzi non c'è
stato, c'è un guasto. Soglia minima dichiarata: almeno **0,60 di peso disponibile** (cioè il nucleo di prezzo, o
MVRV più due indicatori di prezzo). Sotto quella soglia lo stato è `sconosciuto` e il bot lo dice.

### 1.5 Come si combinano: punteggio, non AND né OR

Deciso in F2.2-bis. L'AND stretto non si accende quasi mai (basta un ingrediente fuori posto), l'OR largo si accende
troppo. Il confronto numerico fra le tre logiche è nel §4. Regola:

```
se punteggio_economico >= SOGLIA_STRAORDINARIO e punteggio_economico > punteggio_caro  -> straordinario
se punteggio_caro      >= SOGLIA_FRENO         e punteggio_caro      > punteggio_economico -> freno
altrimenti -> normale
```

I due punteggi restano **separati e mostrati entrambi** (D9: mai fondere ingredienti in disaccordo in un numero solo).

### 1.6 Soglie: calibrate solo sulla quota di giorni

Le due soglie **non** si scelgono guardando le date: si scelgono in modo che la quota storica di giorni accesi cada
nell'intervallo dichiarato nel piano, e basta.

- `SOGLIA_STRAORDINARIO`: la più bassa che tiene lo stato straordinario **≤ 12 %** dei giorni (criterio (c): 10-15 %).
- `SOGLIA_FRENO`: la più bassa che tiene lo stato freno **≤ 20 %** dei giorni (criterio (f): 20-25 %).

Periodo di calibrazione: tutta la storia disponibile con percentili validi (dal 2014, serie CoinMetrics `PriceUSD`,
che è l'unica che arriva prima del 2017 — D22).

### 1.7 Conferma e isteresi

Lo stato cambia solo dopo **2 giorni consecutivi** oltre la soglia. Serve a non far lampeggiare il messaggio di
cambio stato (modo C di D19) su un singolo giorno di rumore. Dichiarato prima del test, non tarato dopo.

### 1.8 Moltiplicatore, colpi e tetto (F2.4 / F2.5)

- Moltiplicatore dello sforzo: `m = 1 + (M_max - 1) × profondità_normalizzata`, con `M_max = 3` e profondità
  normalizzata = (punteggio − soglia) / (1 − soglia), arrotondato a 0,5.
- L'extra si versa in **almeno 3 colpi** (settimanali): mai tutto il primo giorno.
- Tetto per ciclo `C`, in **mesi equivalenti di budget** (200 €/mese oggi, 500 o 1000 domani senza cambiare nulla).
  Allocazione dichiarata in anticipo, per riservare capienza alle fasi più profonde:

  | profondità del punteggio | quota massima **cumulata** del tetto |
  |---|---|
  | da soglia a 0,45 | 30 % |
  | fino a 0,60 | 65 % |
  | oltre 0,60 | 100 % |

  Verifica richiesta dal piano: arrivando al decile più basso deve restare capienza. Il valore di `C` lo decide
  l'utente: nel §5 sono simulati gli scenari 6, 12 e 18 mesi equivalenti per farlo scegliere sui numeri.

### 1.9 Cosa NON è parametrizzato

Nessuna regola di vendita (D16). Nessuna soglia assoluta su prezzo o indicatori. Nessun ingrediente fuori dalla
lista del §1.1.

---

## 2. Risultato del test storico

Comando: `python3 backtest/test_storico_stati.py` (output salvato in `backtest/test_storico_stati_output.txt`).
Serie: `PriceUSD` di CoinMetrics 2010-2026 — serve la storia lunga perché il percentile a 4 anni richiede
quattro anni di passato: partendo dal 2017 non si potrebbero giudicare né il 2018 né il 2020.
Punteggio calcolabile dal **2011-10-23**, su 5.446 giorni.

**Soglie uscite dalla calibrazione** (fatta solo sulla quota di giorni, mai sulle date):
straordinario ≥ **0,4229** · freno ≥ **0,2314**.

Quota di giorni: **straordinario 12,0 % · normale 83,5 % · freno 4,4 %**.

| criterio | esito | numero |
|---|---|---|
| (a) giugno 2026 straordinario | **passa** | acceso dal 6 all'11 e dal 25 al 30 giugno |
| (b) dicembre 2018 | **passa** | 31 giorni su 31 |
| (b) marzo 2020 | **passa** | dal 13 al 31 marzo |
| (b) novembre 2022 | **passa** | 27 giorni |
| (c) straordinario fra il 10 e il 15 % dei giorni | **passa** | 12,0 % |
| (d) nessun giorno straordinario nei 3 mesi prima di un massimo | **passa** | 0 su tutti e quattro i massimi |
| (e) freno vicino ad almeno 3 massimi su 4 | **fallisce** | 2 su 4 — vedi §3 |
| (f) zero freno a inizio rialzo 2020 | **fallisce** | 4 giorni (28-31 dicembre 2020) — vedi §3 |
| (g) stabilità cambiando finestra | **passa a 3, 4 e 5 anni** | cambi di stato 6,8 % e 2,4 %; a 2 anni fuori perimetro |

Rendimento a 12 mesi dei giorni in stato straordinario: **mediana +78 %, 87 % di casi positivi**, contro
+90 % (72 % positivi) di un giorno qualsiasi. Lo stato non "batte il mercato": seleziona giorni in cui la
probabilità di essere in perdita a un anno è molto più bassa della media. È esattamente ciò che serve a
decidere *quanto sforzo* mettere, non *quando* comprare.

---

## 3. Il problema del freno: due criteri incompatibili, dimostrato coi numeri

Il criterio (e) chiede che il freno sia acceso vicino ai massimi; il criterio (f) che sia spento a
novembre-dicembre 2020, all'inizio del rialzo che portò da 16 mila a 60 mila. **Non possono valere insieme**,
e non è una questione di taratura:

| data | prezzo | punteggio "caro" | MVRV | Mayer | RSI settimanale | |
|---|---|---|---|---|---|---|
| 2020-12-15 | 19.433 $ | 0,395 | 2,48 | 1,60 | 84,1 | inizio del rialzo |
| 2020-12-31 | 29.023 $ | 0,721 | 3,14 | 2,17 | 91,6 | inizio del rialzo |
| 2021-11-08 | 67.542 $ | 0,484 | 2,85 | 1,48 | 70,0 | **massimo di ciclo** |
| 2025-10-06 | 124.824 $ | 0,431 | 2,29 | 1,18 | 65,1 | **massimo di ciclo** |

A fine dicembre 2020 il mercato era **più caro, su ogni singolo ingrediente**, di quanto lo fosse ai due
massimi più recenti. Qualunque soglia sul *livello* che si accende a quei massimi si accende anche lì:
27 giorni su 61 di novembre-dicembre 2020 avevano un punteggio "caro" superiore a quello del massimo del 2025.

**Cosa cambia fra i due casi**: non quanto è caro il mercato, ma **da quanto tempo lo è**. Da qui il requisito
di durata (giro 2): il freno si accende solo dopo **60 giorni consecutivi** sopra la soglia. Effetto:

| versione del freno | quota di giorni | entro 12 mesi da un massimo | rendimento a +12 mesi | massimi colti | giorni in nov-dic 2020 |
|---|---|---|---|---|---|
| prudente (nessuna durata) | 20,1 % | 61 % | mediana **+52 %** (65 % positivi) | 4 su 4 | 27 |
| **tardivo (60 giorni)** | **4,4 %** | **79 %** | mediana **−18 %** (41 % positivi) | 2 su 4 | 4 |

**Decisione dell'utente (2026-09-20): freno tardivo.** Un segnale raro che, quando parla, è seguito da 12 mesi
mediamente negativi vale più di un segnale frequente che non distingue nulla. I quattro giorni residui di
dicembre 2020 sono il 28-31, con MVRV 3,03-3,14 e RSI settimanale 91: erano davvero estremi, e in quei giorni
il bot avrebbe detto solo "non aggiungere extra", mai "vendi" (D16).

**Criteri riscritti** (approvati nella stessa decisione, sostituiscono (e) ed (f) nel piano):
- **(e')** il freno dev'essere **raro e informativo**: ≤ 10 % dei giorni, ≥ 60 % dei suoi giorni entro 12 mesi
  da un massimo, rendimento mediano a 12 mesi negativo. → 4,4 % · 79 % · −18 %: **passa**.
- **(f')** il freno dev'essere **quasi muto a inizio rialzo**: ≤ 5 giorni in novembre-dicembre 2020, e solo su
  valori estremi dichiarati. → 4 giorni: **passa**.

I criteri originali restano stampati dal test, marcati come non superati: non sono stati cancellati, sono
stati sostituiti per una ragione scritta.

---

## 4. Le tre logiche di combinazione a confronto (F2.2-bis)

| logica | giorni straordinari | giorni di freno | giugno 2026 | rendimento +12 mesi | positivi |
|---|---|---|---|---|---|
| AND stretto (tutti gli ingredienti in zona) | 9,2 % | 7,3 % | acceso | +51 % | 71 % |
| AND morbido (5 su 7) | 14,8 % | 17,0 % | acceso | +58 % | 79 % |
| OR largo (almeno uno) | 58,7 % | 38,0 % | acceso | +82 % | 73 % |
| **punteggio di profondità (scelto)** | **12,0 %** | **4,4 %** | **acceso** | **+78 %** | **87 %** |

L'OR largo sembra buono finché non si guarda quanto spesso è acceso: il 59 % dei giorni, cioè quasi sempre —
il suo +82 % è praticamente il rendimento di un giorno qualsiasi (+90 %) e la sua quota di casi positivi (73 %)
è quella di base (72 %). L'AND stretto è raro ma seleziona peggio. Il punteggio è l'unico che tiene insieme
rarità e qualità: 12 % dei giorni e 87 % di casi positivi a 12 mesi.

---

## 5. Sforzo, tranche e tetto (F2.4 / F2.5)

Comando: `python3 backtest/simula_sforzo.py` (output in `backtest/simula_sforzo_output.txt`).

> **Aggiornato dopo D41 (2026-09-22).** La correzione della perdita di lookahead negli indicatori settimanali
> e la ricalibrazione delle soglie (0,4257 / 0,2315) hanno abbassato leggermente i risultati. Non è la prova
> che prima si barasse: la versione vecchia non leggeva prezzi futuri, calcolava un indicatore settimanale
> leggermente sbagliato (saltava l'ultima settimana chiusa). Il calo è l'effetto della correzione. Numeri attuali, con tetto 12 mesi equivalenti: **+12,3 % di
> BTC** rispetto al solo ricorrente (18,3566 contro 16,3459) avendo versato il **10,3 %** in più; a parità di
> depositi il tempismo vale **+1,8 %**. La tabella qui sotto è quella **prima** della correzione, lasciata per
> confronto: le conclusioni non cambiano, i numeri sì.
Simulazione 2015-01-01 → 2026-09-19, budget 200 €/mese, fee 0,1 %, decisione settimanale il lunedì.

| scenario | depositato | BTC | BTC col DCA a parità di depositi | differenza | extra versati |
|---|---|---|---|---|---|
| solo ricorrente (nessun bot) | 28.200 € | 16,3459 | — | — | — |
| tetto 6 mesi equivalenti | 30.780 € | 18,3153 | 17,8414 | **+2,7 %** | 2.580 € |
| **tetto 12 mesi equivalenti** | 31.150 € | 18,4677 | 18,0559 | **+2,3 %** | 2.950 € |
| tetto 18 mesi equivalenti | 31.200 € | 18,4724 | 18,0848 | +2,1 % | 3.000 € |
| nessun tetto | 31.200 € | 18,4724 | 18,0848 | +2,1 % | 3.000 € |

**Come si legge, senza illusioni.** La colonna "differenza" è il confronto onesto previsto da D1: a *parità di
depositi*, il tempismo del bot ha aggiunto il **2,3 %** di BTC. Poco — ed è coerente con l'analisi v5.1, che
aveva già misurato che il timing vale quasi nulla. Il beneficio grosso è un altro: **+13,0 % di BTC
(18,47 contro 16,35) avendo versato il 10,5 % in più**. Cioè il bot non serve a indovinare il momento: serve a
farti mettere più soldi quando il mercato è raro, cosa che senza qualcuno che guarda non succede.

Dettaglio per ciclo con tetto 12 (il tetto si azzera quando il prezzo segna un nuovo massimo storico):

| ciclo | periodo | tranche | speso | mesi equivalenti | prezzo medio degli extra | capienza residua |
|---|---|---|---|---|---|---|
| 1 | 2015-01 → 2015-08 | 14 | 425 € | 2,1 | 240 $ | 9,9 mesi |
| 2 | 2018-11 → 2020-03 | 21 | 1.025 € | 5,1 | 4.049 $ | 6,9 mesi |
| 3 | 2022-05 → 2023-01 | 33 | 1.375 € | 6,9 | 20.477 $ | 5,1 mesi |
| 4 | 2026-02 → 2026-06 | 5 | 125 € | 0,6 | 65.393 $ | 7,2 mesi |

Verifiche del piano: la tranche più grande vale 100 €, il **4,2 % del tetto** (richiesto < 10 %); in tutti e
quattro i cicli lo sforzo è spalmato su almeno 3 tranche; nessun ciclo supera il tetto; **arrivando al punto
più profondo restava sempre capienza** (minimo 5,1 mesi equivalenti).

**Il tetto non è mai stato il vincolo**: il ciclo più intenso (2022-23) ha usato 6,9 mesi equivalenti su 12.
Un tetto di 12 mesi è quindi comodo; a 6 mesi il vincolo comincia a mordere (2.580 € invece di 2.950 €).

**Giugno 2026, il caso che ha fatto nascere il progetto**: il bot avrebbe scritto "settimana da 1,5x" l'8 e il
29 giugno, 25 € extra ciascuna a 63.110 $ e 60.175 $ (oggi 81.262 $). Sono cifre piccole perché la fase è
durata poche settimane: lo sforzo è proporzionale alla durata, non solo alla profondità. Se si vuole che una
finestra breve pesi di più, si alza il moltiplicatore minimo — ma è una scelta da fare con gli occhi aperti,
non un difetto da correggere di nascosto.

---

## 6. Contatore delle ri-tarature (regola procedurale di F2.3)

| giro | cosa è cambiato | perché | chi ha deciso |
|---|---|---|---|
| 1 | nessuna modifica: parametri del §1 così com'erano | primo lancio del test | — |
| 2 | aggiunto il requisito di **durata** per il freno (60 giorni) | scoperta l'incompatibilità fra (e) ed (f): il livello non distingue inizio e fine di un rialzo | agente, poi confermato dall'utente |
| 3 | aggiunto il **moltiplicatore minimo 1,5x** in stato straordinario | correzione di coerenza: per i punteggi appena sopra la soglia l'arrotondamento dava 1,0x, cioè "fase straordinaria, versa zero" | agente |

**Nessuna soglia è stata spostata dopo aver visto le date.** Le due soglie restano quelle uscite dalla
calibrazione sulla quota di giorni al primo giro. I giri 2 e 3 hanno cambiato la *struttura* della regola
(durata, minimo del moltiplicatore), non la sua taratura sui casi storici.

---

## 7. Limiti dichiarati

1. **Tre o quattro cicli, non una statistica.** Tutti i numeri qui sopra vengono da 3-4 cicli di mercato.
   Le percentuali con molti decimali non devono ingannare: i giorni si sovrappongono e non sono osservazioni
   indipendenti.
2. **Il percentile a 4 anni è lungo quanto un ciclo.** È in parte auto-referenziale: ogni ciclo produce per
   costruzione i propri decili bassi vicino al proprio minimo. La verifica (g) a 3 e 5 anni serve a questo, e
   regge; a 2 anni no, ed è dichiarato fuori perimetro (finestra più corta di un ciclo).
3. **Il freno coglie 2 massimi su 4.** Non è un rilevatore di massimi e non va raccontato come tale.
4. **Il tempismo vale poco** (+1,8 % a parità di depositi dopo la correzione D41; +2,3 % prima). Il valore del bot è farti versare di più nelle
   fasi rare, non indovinare il minimo.
5. **Il tetto per ciclo non è ancora deciso** dall'utente: finché è `None`, il bot lo dichiara nel messaggio
   invece di proporre tranche. La simulazione dice che 12 mesi equivalenti non è mai stato un vincolo.
6. **Niente di tutto questo è una previsione.** La regola descrive dove si trova il mercato rispetto al
   proprio passato recente; il futuro resta quello che è.

---

## 8. Rendimenti decrescenti: cosa tocca e cosa no

Osservazione dell'utente (2026-09-20), verificata sui nostri dati prima di accettarla. Ampiezza dei cicli
misurata dal minimo al massimo sulla serie `PriceUSD`:

| ciclo | da | a | guadagno |
|---|---|---|---|
| 1 | 2011-11-18 (2 $) | 2013-12-04 (1.135 $) | **+53.814 %** |
| 2 | 2015-01-14 (176 $) | 2017-12-16 (19.641 $) | **+11.082 %** |
| 3 | 2018-12-15 (3.185 $) | 2021-11-08 (67.542 $) | **+2.021 %** |
| 4 | 2022-11-09 (15.758 $) | 2025-10-06 (124.824 $) | **+692 %** |

Ogni ciclo vale fra un terzo e un quinto del precedente (÷4,9 · ÷5,5 · ÷2,9). Le durate invece sono stabili:
25, 35, 35, 35 mesi.

**Cosa NON tocca: il motore.** Proprio perché ragiona a percentili e non a livelli, non si sgonfia con i cicli.
Ai quattro minimi di ciclo l'MVRV assoluto sale di volta in volta (0,42 → 0,56 → 0,69 → 0,75) — cioè le soglie
assolute invecchiano, come già documentato in `docs/02` §2 — ma il **percentile** resta sotto il 3° in tutti e
quattro i casi e il punteggio di profondità resta alto: 0,97 · 0,80 · 0,97 · 0,82. Stessa cosa per il
moltiplicatore massimo raggiunto in ogni fase di accumulo: 3,0x · 2,5x · 3,0x · 3,0x. Il motore continua a
riconoscere gli estremi anche se gli estremi si accorciano.

**Cosa tocca eccome: il premio, quindi il linguaggio dei messaggi.** Rendimento mediano a 12 mesi dei giorni
in stato straordinario, fase per fase:

| fase di accumulo | giorni straordinari | punteggio max | moltiplicatore max | +12 mesi (mediana) |
|---|---|---|---|---|
| 2011-10 → 2013-06 | 61 | 0,98 | 3,0x | **+321 %** |
| 2014-06 → 2016-12 | 169 | 0,80 | 2,5x | **+58 %** |
| 2018-10 → 2020-12 | 146 | 0,97 | 3,0x | **+139 %** |
| 2022-04 → 2026-09 | 276 | 0,94 | 3,0x | **+40 %** |

Il "+78 % mediano" del §2 è la media di un mondo che comprende il 2011. **Il numero rilevante oggi è l'ultimo:
+40 %.** Conseguenze vincolanti per le fasi successive:

1. **F3.2 (confronto storico automatico)**: il bot deve citare **l'episodio comparabile più recente** e non la
   mediana di tutta la storia, oppure mostrare entrambi dicendo che i cicli si stanno accorciando. Promettere
   +78 % (o il +127 % del decile più basso di `docs/02`) sarebbe vendere un mondo che non c'è più.
2. **F3.3 (regola dell'onestà)**: fra le cose che il messaggio deve dire c'è anche questa — l'ampiezza dei cicli
   si sta riducendo, quindi lo stesso segnale vale meno di quanto valeva.
3. **F2.5 (tetto)**: non cambia il meccanismo, ma rafforza la scelta di esprimerlo in mesi equivalenti e di
   non alzarlo a cuor leggero: se il premio atteso si dimezza a ogni ciclo, raddoppiare lo sforzo per
   inseguirlo è esattamente il modo di trasformare una regola prudente in una scommessa.
4. **F6.3 (autopsia a 12 mesi)**: il metro di giudizio va preso dal ciclo corrente, non dalla media storica.


---

## 9. Futuro e passato: lookahead e prova fuori campione (D41)

**Il calcolo non usa il futuro — provato.** `tests/test_lookahead.py` taglia lo storico a otto giorni scelti
(meta' settimana, fine settimana, primo giorno di uno straordinario, massimi, minimi, il 5 giugno 2026) e
pretende che ogni indicatore, lo stato e i punteggi siano identici a quelli calcolati con tutto lo storico.
Alla prima esecuzione **non lo erano**: gli indicatori settimanali usavano la domenica della settimana in corso.
Corretto; da allora il test passa e resta nella suite.

**La regola funziona su anni che non aveva visto?** `backtest/test_fuori_campione.py`:

| soglie calibrate fino al | soglia straord. | anni mai visti | quota straordinario | casi accesi | prima dei massimi | +12 mesi (straord. / qualsiasi) |
|---|---|---|---|---|---|---|
| 2018-12-31 | 0,4148 | 2019 → 2026 | 13,6 % | mar 2020 · nov 2022 · **giu 2026** | mai | **+73 %** / +48 % |
| 2020-12-31 | 0,4181 | 2021 → 2026 | 13,3 % | nov 2022 · **giu 2026** | mai | **+40 %** / +21 % |
| 2022-12-31 | 0,5115 | 2023 → 2026 | **1,1 %** | giu 2026 (5 giorni) | mai | +163 % / +79 % |

Le prime due righe sono la prova più forte che il progetto possa avere prima dei dati veri: una regola scritta
con i dati fino al 2018 avrebbe riconosciuto marzo 2020, novembre 2022 e giugno 2026 senza averli mai visti, e
non si sarebbe mai accesa prima di un massimo. La terza riga è la fragilità da dichiarare: calibrando subito dopo
il 2022 (un mercato orso lungo e profondo) la soglia sale a 0,51 e il bot diventa molto più silenzioso.

**Da qui in avanti i parametri sono congelati.** L'unica prova che nessuno può truccare è il futuro: il registro
giornaliero (D33) salva cosa il bot ha detto quel giorno, e non si riscrive.
