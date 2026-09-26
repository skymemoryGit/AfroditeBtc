"""Il motore dei tre stati (F2.1 del piano) — funzione pura, nessun effetto collaterale.

Prende i **percentili** degli ingredienti del giorno e restituisce lo stato di sforzo:
*straordinario* / *normale* / *freno*, con i punteggi, i motivi e il moltiplicatore suggerito.

Perche' percentili e non valori assoluti: le soglie assolute invecchiano di ciclo in ciclo
(`docs/02` §2: MVRV ai massimi 4,43 -> 2,29, Mayer 3,78 -> 1,18, RSI settimanale 90 -> 65).
Il percentile sulla finestra mobile e' l'unica misura che resta confrontabile tra cicli.

Parametri e ragioni: `docs/04_regola_stati.md` §1, scritto PRIMA del test storico.
Qui non si decide niente di nuovo: si applica quello che c'e' scritto la'.

Nessuna rete, nessun file, nessuna data "di oggi" presa dal sistema: stesso input, stesso output.
"""

STRAORDINARIO = "straordinario"
NORMALE = "normale"
FRENO = "freno"
SCONOSCIUTO = "sconosciuto"

# Pesi dichiarati in docs/04 §1.3. Somma 1,20; il solo nucleo di prezzo vale 0,80.
PESI = {
    "price_vs_wma200": 0.25,
    "mayer": 0.20,
    "dd365": 0.20,
    "rsi14_w": 0.10,
    "rsi14_d": 0.05,
    "mvrv": 0.30,
    "fng": 0.10,
}
NUCLEO_PREZZO = ("price_vs_wma200", "mayer", "dd365", "rsi14_w", "rsi14_d")
ARRICCHIMENTO = ("mvrv", "fng")

ETICHETTE = {
    "price_vs_wma200": "prezzo rispetto alla media a 200 settimane",
    "mayer": "Mayer multiple (prezzo/media 200 giorni)",
    "dd365": "distanza dal massimo dell'ultimo anno",
    "rsi14_w": "RSI settimanale",
    "rsi14_d": "RSI giornaliero",
    "mvrv": "MVRV",
    "fng": "Fear & Greed",
}

# Come si dice ogni ingrediente in una frase, col suo valore dentro: il percentile da solo
# ("percentile 15") non dice niente a un essere umano.
FRASI = {
    "price_vs_wma200": ("prezzo a {v} volte la media a 200 settimane", 2),
    "mayer": ("Mayer multiple a {v}", 2),
    "dd365": ("prezzo a {v}% dal massimo dell'ultimo anno", 0),
    "rsi14_w": ("RSI settimanale a {v}", 0),
    "rsi14_d": ("RSI giornaliero a {v}", 0),
    "mvrv": ("MVRV a {v}", 2),
    "fng": ("Fear & Greed a {v}", 0),
}


def _italiano(numero, decimali):
    return f"{numero:.{decimali}f}".replace(".", ",")


def _del(percentuale):
    """'del 72%' ma 'dell'85%': elisione davanti ai numeri che si leggono con vocale iniziale."""
    testo = f"{percentuale:.0f}"
    return f"dell'{testo}%" if testo.startswith("8") or testo in ("1", "11") else f"del {testo}%"


def _nel(percentuale):
    """'nel 72%' ma 'nell'85%' (stessa elisione di `_del`)."""
    return "n" + _del(percentuale)[1:]


def _intero(numero):
    """1460 -> '1.460': separatore delle migliaia all'italiana."""
    return f"{int(numero):,}".replace(",", ".")


def confronto_in_giorni(piu_alti, totale, anni=4, uguali=0):
    """'negli ultimi 4 anni è stato più alto di oggi in 380 giorni su 1.460 (26%)' (D42).

    Una sola forma per tutti gli indicatori e tutti i messaggi, sempre nello stesso verso
    ("più alto di oggi") e con i giorni veri. La forma precedente, "solo 26 giorni su 100 erano
    più cari di oggi", faceva pensare a cento giorni veri e cambiava verso da una riga all'altra.
    `totale` comprende oggi: oggi non è più alto di se stesso, quindi sta fra i "non più alti".

    `uguali` sono gli altri giorni con lo stesso identico valore di oggi. Contano davvero in due
    casi: il drawdown, che vale 0 in ogni giorno di nuovo massimo annuale (il 30/12/2020 erano 121
    giorni su 1.460), e il Fear & Greed, che e' un intero. Si dicono quando pesano almeno l'1%,
    altrimenti "il valore più alto" farebbe credere a un caso unico.
    """
    pareggi = uguali > 0 and 100.0 * uguali >= totale
    if piu_alti <= 0:
        if uguali > 0:
            return (f"negli ultimi {anni} anni non è mai stato più alto di oggi "
                    f"(uguale in {_intero(uguali)} giorni su {_intero(totale)})")
        return f"il valore più alto degli ultimi {anni} anni"
    if piu_alti >= totale - 1:
        return f"il valore più basso degli ultimi {anni} anni"
    quota = 100.0 * piu_alti / totale
    testo_quota = "meno dell'1%" if quota < 0.5 else f"{quota:.0f}%"
    return (f"negli ultimi {anni} anni è stato più alto di oggi in {_intero(piu_alti)} giorni "
            f"su {_intero(totale)} ({testo_quota})"
            + (f", uguale in altri {_intero(uguali)}" if pareggi else ""))


class Parametri:
    """Tutti i numeri della regola. Valori predefiniti = quelli dichiarati in docs/04 §1."""

    def __init__(self, percentile_economico=30.0, percentile_caro=70.0,
                 soglia_straordinario=None, soglia_freno=None,
                 peso_minimo=0.60, molt_max=3.0, molt_min=1.5, colpi_minimi=3, conferma_giorni=2,
                 pesi=None, bande_tetto=((0.45, 0.30), (0.60, 0.65), (1.01, 1.00)),
                 durata_minima_caro=0):
        self.percentile_economico = percentile_economico
        self.percentile_caro = percentile_caro
        self.soglia_straordinario = soglia_straordinario
        self.soglia_freno = soglia_freno
        self.peso_minimo = peso_minimo
        self.molt_max = molt_max
        # Se lo stato e' straordinario, lo sforzo suggerito non puo' essere "niente": senza questo
        # minimo, per i punteggi appena sopra la soglia l'arrotondamento dava 1,0x e il bot avrebbe
        # detto "fase straordinaria" proponendo zero euro. Scoperto dalla simulazione F2.4
        # (docs/04 §5, giro 3): e' una correzione di coerenza, non una taratura sulle date.
        self.molt_min = molt_min
        self.colpi_minimi = colpi_minimi
        self.conferma_giorni = conferma_giorni
        self.pesi = dict(pesi or PESI)
        self.bande_tetto = tuple(bande_tetto)
        # Giorni consecutivi sopra la soglia richiesti PRIMA che il freno possa accendersi.
        # Motivo (giro 2 del test storico, docs/04 §4): il livello da solo non distingue
        # "inizio di un rialzo" da "fine di un rialzo" — a dicembre 2020 il mercato era piu'
        # caro che ai massimi del 2021 e del 2025. Quello che cambia e' da QUANTO TEMPO e' caro.
        self.durata_minima_caro = durata_minima_caro

    def copia(self, **cambi):
        nuovo = Parametri(self.percentile_economico, self.percentile_caro,
                          self.soglia_straordinario, self.soglia_freno, self.peso_minimo,
                          self.molt_max, self.molt_min, self.colpi_minimi, self.conferma_giorni,
                          self.pesi, self.bande_tetto, self.durata_minima_caro)
        for chiave, valore in cambi.items():
            setattr(nuovo, chiave, valore)
        return nuovo

# ------------------------------------------------------------- profondita'

def profondita_economica(percentile, limite):
    """0 sopra il limite, 1 al percentile 0. Rampa lineare (docs/04 §1.2)."""
    if percentile is None:
        return None
    return max(0.0, (limite - percentile) / limite)


def profondita_cara(percentile, limite):
    """0 sotto il limite, 1 al percentile 100."""
    if percentile is None:
        return None
    return max(0.0, (percentile - limite) / (100.0 - limite))

# ------------------------------------------------------------- valutazione

def valuta(percentili, parametri=None, valori=None):
    """Da percentili degli ingredienti a stato del giorno. Funzione pura.

    percentili: {"mayer": 12.3, "mvrv": None, ...} — None = ingrediente non disponibile.
    valori:     opzionale, i valori grezzi, usati solo per scrivere i motivi in chiaro.

    Ritorna un dizionario con: stato (senza conferma: e' `serie_stati` a gestirla),
    punteggio_economico, punteggio_caro, peso_disponibile, contributi, ingredienti_mancanti,
    moltiplicatore, motivi.
    """
    p = parametri or Parametri()
    contributi, peso_disponibile = {}, 0.0
    somma_eco = somma_caro = 0.0
    mancanti = []

    for chiave, peso in p.pesi.items():
        pct = percentili.get(chiave)
        if pct is None:
            mancanti.append(chiave)
            continue
        eco = profondita_economica(pct, p.percentile_economico)
        caro = profondita_cara(pct, p.percentile_caro)
        contributi[chiave] = {"percentile": pct, "economico": eco, "caro": caro, "peso": peso}
        peso_disponibile += peso
        somma_eco += peso * eco
        somma_caro += peso * caro

    if peso_disponibile < p.peso_minimo:
        return {"stato": SCONOSCIUTO, "punteggio_economico": None, "punteggio_caro": None,
                "peso_disponibile": peso_disponibile, "contributi": contributi,
                "ingredienti_mancanti": mancanti, "moltiplicatore": None,
                "motivi": [f"ingredienti insufficienti: peso disponibile {peso_disponibile:.2f} "
                           f"sotto il minimo {p.peso_minimo:.2f}"]}

    eco = somma_eco / peso_disponibile
    caro = somma_caro / peso_disponibile

    stato = NORMALE
    if p.soglia_straordinario is not None and eco >= p.soglia_straordinario and eco > caro:
        stato = STRAORDINARIO
    elif p.soglia_freno is not None and caro >= p.soglia_freno and caro > eco:
        stato = FRENO

    return {"stato": stato, "punteggio_economico": eco, "punteggio_caro": caro,
            "peso_disponibile": peso_disponibile, "contributi": contributi,
            "ingredienti_mancanti": mancanti,
            "moltiplicatore": moltiplicatore(eco, p) if stato == STRAORDINARIO else None,
            "motivi": motivi(contributi, stato, valori)}


def moltiplicatore(punteggio_economico, parametri=None):
    """Da profondita' a numero concreto: 1x alla soglia, M_max al punteggio pieno (docs/04 §1.8)."""
    p = parametri or Parametri()
    if p.soglia_straordinario is None or punteggio_economico is None:
        return None
    denominatore = max(1e-9, 1.0 - p.soglia_straordinario)
    normalizzata = min(1.0, max(0.0, (punteggio_economico - p.soglia_straordinario) / denominatore))
    grezzo = 1.0 + (p.molt_max - 1.0) * normalizzata
    return max(p.molt_min, round(grezzo * 2) / 2.0)      # arrotondato a 0,5, mai sotto il minimo


def motivi(contributi, stato, valori=None, quanti=3, conteggi=None):
    """I tre ingredienti che pesano di piu' sullo stato, in italiano leggibile.

    conteggi: opzionale, {ingrediente: {"piu_alti", "totale", "anni"}} contati sulla stessa
    finestra dei percentili (li calcola `messaggi.quanti_piu_alti`). Se ci sono, la frase usa i
    giorni veri; se no, la stessa frase in percentuale. Il verso e' sempre lo stesso (D42).
    """
    if not contributi:
        return []
    verso = "economico" if stato == STRAORDINARIO else ("caro" if stato == FRENO else None)
    if verso is None:
        # in stato normale si dice comunque cosa e' piu' vicino a muoversi
        ordinati = sorted(contributi.items(),
                          key=lambda kv: max(kv[1]["economico"], kv[1]["caro"]) * kv[1]["peso"],
                          reverse=True)
    else:
        ordinati = sorted(contributi.items(), key=lambda kv: kv[1][verso] * kv[1]["peso"], reverse=True)
    righe = []
    for chiave, c in ordinati[:quanti]:
        if verso and c[verso] <= 0:
            continue
        modello, decimali = FRASI.get(chiave, ("{v} (" + chiave + ")", 2))
        valore = (valori or {}).get(chiave)
        pezzo = (modello.format(v=_italiano(valore, decimali)) if valore is not None
                 else ETICHETTE.get(chiave, chiave))
        pct = c["percentile"]
        # Un verso solo, per ogni ingrediente e in ogni stato (D42): "più alto di oggi in N giorni
        # su M". Prima la frase passava da "più basso del..." a "più alto del..." a seconda
        # dell'ingrediente, e chi legge doveva rifare il ragionamento al contrario a ogni riga.
        conto = (conteggi or {}).get(chiave)
        if conto:
            confronto = confronto_in_giorni(conto["piu_alti"], conto["totale"], conto.get("anni", 4),
                                            conto.get("uguali", 0))
        elif pct >= 99.5:
            confronto = "il valore più alto degli ultimi 4 anni"
        elif pct <= 0.5:
            confronto = "il valore più basso degli ultimi 4 anni"
        else:
            confronto = f"negli ultimi 4 anni è stato più alto di oggi {_nel(100 - pct)} dei giorni"
        righe.append(f"{pezzo}: {confronto}")
    return righe

# --------------------------------------------------- serie e conferma

def serie_stati(percentili_per_giorno, parametri=None, valori_per_giorno=None):
    """Applica `valuta` giorno per giorno e poi la regola di conferma (docs/04 §1.7).

    Lo stato cambia solo dopo `conferma_giorni` giorni consecutivi oltre la soglia: evita che il
    messaggio di cambio stato lampeggi su un giorno isolato di rumore. Sequenziale ma pura:
    stessa sequenza in ingresso, stessa in uscita.
    """
    p = parametri or Parametri()
    grezzi = [valuta(pct, p, (valori_per_giorno or [None] * len(percentili_per_giorno))[i])
              for i, pct in enumerate(percentili_per_giorno)]
    stabile = NORMALE
    candidato, contatore = None, 0
    giorni_caro = 0
    for riga in grezzi:
        # da quanti giorni consecutivi il mercato e' sopra la soglia "caro"
        sopra_caro = (riga["punteggio_caro"] is not None and p.soglia_freno is not None
                      and riga["punteggio_caro"] >= p.soglia_freno)
        giorni_caro = giorni_caro + 1 if sopra_caro else 0
        riga["giorni_caro_consecutivi"] = giorni_caro
        proposto = riga["stato"]
        if proposto == FRENO and giorni_caro < p.durata_minima_caro:
            # caro ma non ancora maturo: e' un rialzo giovane, non una fase da freno
            proposto = NORMALE
            riga["stato"] = NORMALE
            riga["motivi"] = riga["motivi"] + [
                f"mercato caro da {giorni_caro} giorni: sotto i {p.durata_minima_caro} "
                f"richiesti perché sia una fase matura"]
        if proposto == SCONOSCIUTO:
            riga["stato_confermato"] = SCONOSCIUTO
            candidato, contatore = None, 0
            continue
        if proposto == stabile:
            candidato, contatore = None, 0
        else:
            if proposto == candidato:
                contatore += 1
            else:
                candidato, contatore = proposto, 1
            if contatore >= p.conferma_giorni:
                stabile = proposto
                candidato, contatore = None, 0
        riga["stato_confermato"] = stabile
    return grezzi

# ------------------------------------------- logiche alternative (F2.2-bis)

def stato_con_and(percentili, parametri=None, quanti_minimo=None):
    """AND stretto: acceso solo se TUTTI gli ingredienti disponibili sono nella loro zona."""
    p = parametri or Parametri()
    disponibili = [(k, v) for k, v in percentili.items() if v is not None and k in p.pesi]
    if not disponibili:
        return SCONOSCIUTO
    minimo = quanti_minimo or len(disponibili)
    eco = sum(1 for _, v in disponibili if v <= p.percentile_economico)
    caro = sum(1 for _, v in disponibili if v >= p.percentile_caro)
    if eco >= minimo:
        return STRAORDINARIO
    if caro >= minimo:
        return FRENO
    return NORMALE


def stato_con_or(percentili, parametri=None):
    """OR largo: basta un ingrediente nella sua zona."""
    p = parametri or Parametri()
    disponibili = [v for k, v in percentili.items() if v is not None and k in p.pesi]
    if not disponibili:
        return SCONOSCIUTO
    if any(v <= p.percentile_economico for v in disponibili):
        return STRAORDINARIO
    if any(v >= p.percentile_caro for v in disponibili):
        return FRENO
    return NORMALE

# ------------------------------------------------ tetto e tranche (F2.5)

def tranche_consentita(punteggio_economico, speso_mesi, tetto_mesi, parametri=None):
    """Quanto sforzo straordinario e' ancora consentito, in mesi equivalenti di budget.

    Le bande di docs/04 §1.8 riservano capienza alle fasi piu' profonde: finche' il punteggio e'
    appena sopra la soglia si puo' spendere al massimo il 30 % del tetto, e cosi' via.
    Ritorna il massimo cumulato ancora disponibile (>= 0). Con tetto None ritorna None: il bot
    deve dichiarare che il tetto non e' stato deciso, non inventarne uno.
    """
    p = parametri or Parametri()
    if tetto_mesi is None or punteggio_economico is None:
        return None
    quota = p.bande_tetto[-1][1]
    for limite, frazione in p.bande_tetto:
        if punteggio_economico < limite:
            quota = frazione
            break
    return max(0.0, quota * tetto_mesi - speso_mesi)
