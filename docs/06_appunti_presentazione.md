# Appunti per la presentazione — AphroditeBTC

Fase F7 del piano. **Bozza dei contenuti, slide per slide**, per chi riceve il bot senza nessun contesto.
Non è ancora la presentazione: è il materiale da cui costruirla. Ogni numero ha la sua fonte fra parentesi
quadre; se un numero non torna, si rilancia lo script indicato — non si corregge a mano.

Regola di scrittura per tutte le slide: **prima l'obiettivo, poi il come**. Niente parola tecnica senza la sua
traduzione accanto. Se una slide ha bisogno di una spiegazione a voce per essere capita, è scritta male.

---

## Slide 1 — Titolo

**AphroditeBTC**
*Love the asset. Analyze the market.*

Sottotitolo: *Un assistente che guarda Bitcoin ogni giorno al posto tuo, e ti avvisa quando vale la pena
mettere qualcosa in più.*

Visivo: l'avatar (la dea con l'alloro e il ₿).

---

## Slide 2 — Il problema (la storia che fa capire tutto)

**Giugno 2026.** Bitcoin è sceso fino alla sua media degli ultimi quattro anni — una cosa che capita poche
volte per ciclo. Era il momento di comprare un po' di più.

Nessuno se n'è accorto in tempo. **Non mancava l'informazione: mancava qualcuno che guardasse quel giorno.**

Da dire a voce: tutti gli indicatori erano disponibili, gratis, su internet. Il problema non era sapere, era
guardare ogni giorno per mesi senza stancarsi.

---

## Slide 3 — Cosa fa, in una frase

**Ogni mattina guarda sette indicatori e ti dice in quale fase è il mercato. Non compra e non vende niente.**

Tre punti sotto:
- ti scrive due righe al giorno (o solo quando serve, se preferisci);
- ti avvisa quando si apre una fase rara ed economica;
- ti dice sempre con quali dati ha deciso e di che giorno sono.

---

## Slide 4 — Il semaforo

Il cuore del prodotto. Tre colori, e ognuno dice **cosa fare con il versamento del mese**:

| | fase | cosa vuol dire per te |
|---|---|---|
| 🟢 | **straordinario** | fase rara ed economica: vale versare di più, spalmato su più settimane |
| ⚪️ | **normale** | nessun estremo: il versamento di sempre, e basta |
| 🔴 | **freno** | mercato caro da mesi: nessun extra (non vuol dire vendere) |

E due avvisi dentro il "normale":
- 🟡 **in arrivo** — lo straordinario sta per scattare, domani si conferma;
- 🟠 **caldo** — il mercato è tirato: niente extra.

Da dire a voce: *il bot non dice mai "vendi"*. Il lato "caro" dei mercati è molto meno prevedibile di quello
"economico", e i dati lo dimostrano (slide 10).

---

## Slide 5 — Come decide (1): 1.460 giorni in fila

La metafora che sblocca tutto. Si usa **al posto della parola "percentile"**, e con i giorni veri:
la versione "su 100" faceva pensare a cento giorni veri (D42).

> Gli ultimi quattro anni sono 1.460 giorni. In quanti di questi l'indicatore era più alto di oggi?

- **in 1.236 giorni su 1.460 (85%)** → quasi sempre più alto: oggi è a sconto (MVRV del 29/06/2026);
- **in 777 giorni su 1.460 (53%)** → a metà: niente di speciale (MVRV del 21/09/2026);
- **in 386 giorni su 1.460 (26%)** → quasi sempre più basso: oggi è caro (Mayer del 21/09/2026).

Una regola sola, uguale per tutti e sette gli indicatori: **pochi giorni più alti = caro, tanti = a sconto.**

Visivo: una fila di 1.460 trattini, con quelli "più alti di oggi" colorati.

---

## Slide 6 — Come decide (2): i due termometri

Dai sette indicatori escono **due termometri separati**:
- **quanto è ECONOMICO** — conta solo chi sta nei primi 30 posti della fila, e più è in fondo più pesa;
- **quanto è CARO** — lo stesso, dall'altra parte.

Il bot li mostra come **quanta strada manca**:

```
quanto è ECONOMICO  ▯▯▯▯▯   0% della strada
quanto è CARO       ▮▮▯▯▯  31% della strada
```

Al 100% della strada economica si accende il 🟢. Al 100% di quella cara (per due mesi di fila) il 🔴.

Da dire a voce: sono due termometri e non uno perché possono dire cose diverse nello stesso giorno, e
quando litigano è un'informazione, non un errore.

---

## Slide 7 — Un esempio vero: oggi contro giugno

La slide che convince. Stessi sette indicatori, due giorni diversi [`docs/tracking/2026-09-22_sessione-11.md`,
rigenerabile con `backtest/messaggi_storici.py`].

| indicatore | 21 settembre 2026 | 29 giugno 2026 |
|---|---|---|
| MVRV | posto 43 · a metà | **posto 15 · zona rara** |
| prezzo / media 4 anni | posto 41 · a metà | **posto 18** |
| Mayer (media 200 giorni) | posto 62 · a metà | **posto 15** |
| distanza dal massimo | posto 29 · appena dentro | **posto 16** |
| RSI settimanale | posto 59 | **posto 9** |
| Fear & Greed | posto 77 · avidità | **posto 3 · paura estrema** |
| RSI giornaliero | posto 81 · caldo | **posto 6** |
| **risultato** | ⚪️ normale · 1 su 7 a sconto, per un soffio | 🟢 **straordinario · 7 su 7 a sconto** |

Messaggio chiave: *oggi un indicatore su sette è a sconto, per un soffio. A giugno lo erano tutti e sette,
e parecchio.*

---

## Slide 8 — Perché non usa soglie fisse

**Le soglie fisse invecchiano.** Il valore di MVRV ai quattro massimi di ciclo [`docs/02` §2]:

| 2017 | apr 2021 | nov 2021 | 2025 |
|---|---|---|---|
| **4,43** | 3,43 | 2,85 | **2,29** |

Chi nel 2025 aspettava "MVRV sopra 4 = euforia" aspettava un numero che non è più tornato. Stessa cosa per il
Mayer (3,78 → 1,18), per l'RSI settimanale (90 → 65), per le ricerche su Google (100 → 32).

Per questo il bot confronta sempre **con gli ultimi 4 anni**, non con un numero scritto una volta per sempre.

Visivo: grafico a barre dei quattro massimi, che scendono.

---

## Slide 9 — Quanto vale, detto onestamente

Simulazione 2015 → 2026, versamento di 200 €/mese [`backtest/simula_sforzo.py`, `docs/04` §5]:

- **+12,3% di bitcoin** rispetto al solo versamento fisso, avendo messo **il 10,3% di soldi in più**;
- a parità di soldi versati, il "tempismo" da solo vale **+1,8%**.

Messaggio chiave: *il bot non indovina il minimo. Ti fa mettere più soldi quando il mercato è raro — cosa che,
senza qualcuno che guarda, non succede.*

---

## Slide 10 — Il test sulla storia

La regola è stata scritta **prima** di guardare i risultati, e poi fatta girare su 15 anni di dati
[`backtest/test_storico_stati.py`, `docs/04` §2].

Si è accesa a:
- dicembre 2018 · marzo 2020 · novembre 2022 · **giugno 2026**

E **non si è mai accesa nei tre mesi prima di un massimo di ciclo**, in nessuno dei quattro cicli. È questo
che protegge dal mettere il bonus nel momento sbagliato.

Stato straordinario: il **12%** dei giorni. Abbastanza raro da contare, abbastanza frequente da servire.

**La prova più forte (fuori campione)**: se la regola fosse stata tarata **solo con i dati fino al 2018**,
negli anni 2019-2026 — che non aveva mai visto — si sarebbe accesa a marzo 2020, novembre 2022 e giugno 2026,
e mai prima di un massimo [`backtest/test_fuori_campione.py`, `docs/04` §9].
Da dire a voce: *giugno 2026 era il caso da cui è nato il progetto, quindi non basta dire "si accende a
giugno". Conta che si accenda su anni che non conosceva.*

Visivo: linea del prezzo 2017-2026 in scala logaritmica, con le fasce verdi dove il bot si accendeva.

---

## Slide 11 — Cosa il bot NON sa (la slide dell'onestà)

- **La storia è corta**: tre o quattro cicli di mercato. Nessun numero qui è una legge.
- **Il freno coglie due massimi su quattro**: non è un rilevatore di massimi, e non va venduto come tale.
- **I cicli si accorciano**: dal minimo al massimo +53.814% → +11.082% → +2.021% → **+692%**. Stesso segnale,
  premio più piccolo ogni volta [`docs/04` §8].
- **Una fase economica può durare e peggiorare**: nel 2022 il prezzo è rimasto 177 giorni sotto la media a
  4 anni, fino a −34%. Per questo lo sforzo si spalma, non si mette tutto il primo giorno.
- **Non è un consulente finanziario.** Descrive il mercato; le decisioni restano di chi lo usa.

---

## Slide 12 — Cosa riceve chi lo usa

Screenshot veri dal telefono:
- il **polso** di due righe, ogni mattina;
- il **messaggio di cambio stato**, l'unico che fa rumore;
- **/analisi** — il report completo a richiesta;
- **/perche** — come ha calcolato lo stato di oggi, indicatore per indicatore;
- **/silenzioso** — scrive solo quando cambia lo stato.

---

## Slide 13 — Sicurezza e privacy

- **Non tocca soldi e non ha chiavi di nessun exchange**: non può comprare né vendere, nemmeno volendo.
- **È personale**: risponde solo alle persone autorizzate dal proprietario. A tutti gli altri dice solo il loro
  identificativo, così possono chiedere l'accesso.
- **Usa solo fonti pubbliche e gratuite**: Coinbase, CoinMetrics, alternative.me.
- **Se un dato manca, lo dice.** Non inventa numeri e non mostra un dato vecchio come se fosse di oggi.

---

## Slide 14 — Come è fatto (per chi è tecnico)

```
tre fonti pubbliche → archivio giornaliero → motore dei tre stati → messaggi → Telegram
```

- motore scritto come funzione pura: stesso ingresso, stessa uscita, testabile;
- **73 test automatici**; test storico riproducibile con uno script;
- tutte le decisioni scritte, con la ragione (`docs/00_decisioni.md`, 40 voci).

---

## Slide 15 — Cosa manca e cosa viene dopo

- **messa in esercizio su un server**, così il bot lavora anche a computer spento;
- **12 mesi di diario**: ogni giorno il bot registra cosa ha visto e cosa ha detto;
- **verifica a 3, 6 e 12 mesi**: ha parlato nei momenti giusti? Se no, si spegne o si cambia.

Messaggio di chiusura: *il criterio di successo è stato scritto prima di cominciare.*

---

## Note per chi costruirà le slide

- **Tono**: sobrio, niente "rendimenti garantiti", niente razzi e lune. Il prodotto è credibile proprio perché
  dice i suoi limiti.
- **Colori**: nero, oro, rosso scuro — quelli dell'avatar. Verde/grigio/rosso solo per il semaforo.
- **Grafici da generare dai dati** (non disegnare a mano): i quattro massimi di MVRV che scendono (slide 8), il
  prezzo con le fasce verdi (slide 10), la fila dei 100 giorni (slide 5).
- **Spiegazioni da rendere ancora più semplici** rispetto a queste note: l'utente ha chiesto esplicitamente che
  nella versione finale siano "ancora più easy". Test pratico: una persona che non sa niente di Bitcoin deve
  poter rispondere a "in che fase siamo oggi?" guardando solo le slide 4, 5 e 6.
