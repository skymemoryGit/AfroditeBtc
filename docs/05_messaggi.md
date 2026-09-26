# I messaggi del bot — regole, esempi, verifiche

Sessione 09 · 2026-09-21 · Fase F3 del piano. Codice: `botbtc/messaggi.py`.
Esempi veri su dieci date storiche: `backtest/messaggi_storici_output.txt`
(si rigenerano con `python3 backtest/messaggi_storici.py`).

## 1. Le regole di scrittura

Non sono questioni di stile: vengono dalle decisioni del progetto.

1. **Nessun ordine.** Il bot descrive e suggerisce uno sforzo. Mai "compra", mai "vendi" (D16).
   Un test cerca gli imperativi e fallisce se ne trova.
2. **Ogni messaggio dichiara la data dei dati usati**, MVRV compreso — che arriva sempre con un
   giorno di ritardo (`docs/02` §1).
3. **Ogni messaggio di stato straordinario dice che la fase può durare e peggiorare**, citando il
   2022: 177 giorni sotto la media a 200 settimane, fino a −34 %.
4. **Il confronto storico cita l'episodio comparabile più recente**, non la mediana di tutta la
   storia: i cicli si accorciano e il premio con loro (D30).
5. **I percentili non si stampano da soli, e si dicono con i giorni veri** (D42). "Percentile 15"
   non dice niente, e nemmeno "15 giorni su 100", che fa pensare a cento giorni veri. Diventa:
   "MVRV a 1,13: negli ultimi 4 anni è stato più alto di oggi in 1.236 giorni su 1.460 (85%)".
   **Verso sempre uguale** ("più alto di oggi") in ogni riga e in ogni stato: pochi giorni più alti
   = oggi è caro, tanti = oggi è a sconto. Quando l'indicatore entra nel punteggio lo si scrive
   accanto ("zona cara" / "zona economica"), con le stesse regole del motore. I pareggi si dicono
   quando pesano almeno l'1% (il drawdown vale 0 in ogni giorno di nuovo massimo annuale).
   Il conto lo fa `messaggi.quanti_piu_alti`, sulla stessa finestra dei percentili, senza lookahead.

## 2. I tre formati (D19)

**Polso** — ogni giorno, due righe, silenzioso. Contiene la riga di avvicinamento, che è il pezzo
che a giugno 2026 sarebbe servito davvero: non "sei arrivato", ma "ti stai avvicinando".

```
BTC 60.175 $ · STRAORDINARIO — fase rara ed economica: varrebbe versare più del solito, in più colpi
A 4% sotto la media a 200 settimane · settimana da 1,5x (~25 EUR in più, in più colpi) · dati del 29/06 · MVRV del 29/06.
```

In stato normale la seconda riga dice quanto manca alla soglia; in stato freno, da quanti giorni il
mercato è caro di fila.

**Cambio di stato** — solo quando lo stato cambia davvero: è l'unico messaggio che chiede attenzione.
Contiene il perché (i tre ingredienti che pesano di più, tradotti in italiano), lo sforzo suggerito
con il saldo del tetto, l'avvertenza sulla durata e il confronto storico. Esempio del 09/11/2022,
accorciato: *«MVRV a 0,75: negli ultimi 4 anni è stato più alto di oggi in 1.449 giorni su 1.460 (99%);
prezzo a 0,66 volte la media a 200 settimane: il valore più basso degli ultimi 4 anni […] L'ultima fase simile è cominciata il
02/06/2022 — da lì: dopo 6 mesi −44 %, dopo 12 mesi −11 %.»* — nota che il precedente citato è
negativo: il bot non sceglie gli esempi che gli fanno comodo.

**Analisi completa** — su richiesta. Tutti gli indicatori col loro percentile, i due punteggi, lo
sforzo, i limiti, il Pi Cycle come contesto. Sta in un solo messaggio Telegram: ~1.400 caratteri
contro i 4.096 consentiti.

## 3. Verifiche fatte

- **14 test automatici** (`tests/test_f3.py`): lunghezza del polso e dell'analisi, presenza della
  data dei dati, avvertenza obbligatoria nello straordinario, assenza di imperativi, saldo del tetto,
  episodio citato = il più recente. Totale del progetto: **56 test verdi**.
- **Lettura umana** dei messaggi su dieci date storiche (dicembre 2018, marzo 2020, dicembre 2020,
  novembre 2021, giugno 2022, novembre 2022, ottobre 2025, giugno 2026, oggi). Correzioni fatte
  rileggendoli: il polso era di quattro righe, i numeri erano all'inglese ("1.5x"), i motivi
  stampavano "percentile 15", gli ingredienti mancanti si chiamavano `fng`, e il messaggio di
  freno non diceva da quanto tempo il mercato fosse caro.

## 4. Un controllo che valeva la pena fare

Le soglie del motore sono state calibrate sulla serie **CoinMetrics** (storia dal 2010), ma il bot
live usa le chiusure **Coinbase** (D22), disponibili subito. Gli stati coincidono?

| periodo | giorni confrontati | stati diversi |
|---|---|---|
| tutto il periodo comune (dal 2018-04) | 3.085 | 251 (**8,1 %**) |
| da quando la finestra a 4 anni di Coinbase è piena (2021→) | 2.086 | 21 (**1,0 %**) |

Le differenze stanno quasi tutte prima del 2021, quando la storia Coinbase (che parte dal 2017) non
bastava a riempire la finestra di quattro anni. Da lì in poi le due serie raccontano la stessa cosa:
ultimo disaccordo l'8 aprile 2024. Giugno 2026 si accende su entrambe per gli stessi 12 giorni.
**Conseguenza pratica**: il bot live può usare Coinbase senza rifare la calibrazione, ma i test
storici che arrivano prima del 2021 vanno fatti sulla serie CoinMetrics.

## 5. Cosa manca ancora

- Il tetto per ciclo non è deciso: finché è `None` i messaggi lo dichiarano invece di inventarlo.
- Il testo non è ancora passato da Telegram: formattazione, lunghezza reale sul telefono e comandi
  sono la fase F4.
