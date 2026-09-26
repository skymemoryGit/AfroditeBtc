"""Il testo dei messaggi (F3 del piano) — da numeri a frasi in italiano.

Tre formati (D19):
- **polso**: due o tre righe, tutti i giorni, silenzioso. E' la rete di sicurezza per gli ingressi
  lenti in zona: contiene la **riga di avvicinamento** (quanto manca alle soglie e in che direzione
  ci si sta muovendo), perche' a giugno 2026 il problema non e' stato mancare un annuncio, e' stato
  non vedere il mercato avvicinarsi per settimane;
- **cambio di stato**: esteso, con il perche', lo sforzo suggerito e i limiti;
- **analisi completa**: su richiesta, tutti gli indicatori. Sta in un solo messaggio Telegram.

Regole di scrittura, non negoziabili (F3.3 + D16 + D30):
1. **nessun ordine**: il bot descrive e suggerisce uno sforzo, non dice mai "compra" o "vendi";
2. **ogni messaggio dichiara la data dei dati usati**, MVRV compreso (arriva a T+1);
3. **ogni messaggio di stato straordinario dice che la fase puo' durare e peggiorare**: nel 2022 il
   prezzo e' stato 177 giorni sotto la media a 200 settimane, fino a -34 %;
4. **il confronto storico cita l'episodio comparabile piu' recente**, non la mediana di tutta la
   storia: l'ampiezza dei cicli si sta riducendo e il premio con essa (docs/04 §8);
5. **i percentili non si stampano da soli**: si traducono in cose concrete ("a 3 % dalla media a
   200 settimane"), il percentile va fra parentesi.

Solo libreria standard. Nessuna rete, nessun file: entra un Dataset gia' pronto, esce testo.
"""

import datetime

from . import engine

# --- fatti storici citabili, tutti verificati e con la fonte nel progetto
FATTO_2022 = ("nel 2022 il prezzo è rimasto 177 giorni sotto la media a 200 settimane, "
              "fino a -34% (docs/02 §5)")

NOMI_STATO = {
    engine.STRAORDINARIO: "STRAORDINARIO",
    engine.NORMALE: "normale",
    engine.FRENO: "FRENO",
    engine.SCONOSCIUTO: "dati insufficienti",
}

SPIEGAZIONE_STATO = {
    engine.STRAORDINARIO: "fase rara ed economica: varrebbe versare più del solito, in più colpi",
    engine.NORMALE: "nessun estremo: il ricorrente e basta",
    engine.FRENO: "fase cara da mesi: nessun versamento extra (non è un invito a vendere)",
    engine.SCONOSCIUTO: "non ho abbastanza ingredienti per dire in che fase siamo",
}


# --- "caldo": una VISTA, non uno stato del motore (D40) -----------------------------------
# Il freno scatta solo dopo 60 giorni di fila sopra la soglia "caro" (D27). Ai due massimi piu'
# recenti (08/11/2021 e 06/10/2025) il punteggio caro era 0,41 e 0,43 — quasi il doppio della
# soglia — ma la serie calda non era mai durata 60 giorni, quindi lo stato era "normale" e il
# messaggio diceva "nessun estremo". Nel giorno esatto del massimo di ciclo. Era falso.
# Il caldo non tocca il motore ne' le soglie calibrate: cambia solo come il messaggio racconta
# la giornata. Non manda notifiche di cambio stato (e' circa un giorno su sette) e non dice mai
# "vendi": dicembre 2020 era piu' caldo e piu' lungo dei due massimi, e il prezzo triplico'.
CALDO = "caldo"
# Il caso speculare, trovato da un test: il punteggio ECONOMICO ha gia' passato la soglia ma lo
# stato non e' ancora confermato (servono 2 giorni di fila). E' il primo giorno di una fase come
# giugno 2026 — il piu' importante da non raccontare come "nessun estremo".
IN_ARRIVO = "in_arrivo"


def condizione(valutazione, parametri):
    """Come raccontare la giornata: straordinario, in arrivo, freno, caldo, normale o sconosciuto."""
    stato = valutazione.get("stato_confermato", valutazione.get("stato"))
    if stato != engine.NORMALE:
        return stato
    caro = valutazione.get("punteggio_caro")
    eco = valutazione.get("punteggio_economico")
    if (eco is not None and parametri.soglia_straordinario is not None
            and eco >= parametri.soglia_straordinario and (caro is None or eco > caro)):
        return IN_ARRIVO
    if (caro is not None and parametri.soglia_freno is not None and caro >= parametri.soglia_freno
            and (eco is None or caro > eco)):
        return CALDO
    return engine.NORMALE


def vista_stato(valutazione, parametri):
    """Icona, titolo e spiegazione da mostrare in testa a ogni messaggio."""
    chiave = condizione(valutazione, parametri)
    if chiave == CALDO:
        giorni = valutazione.get("giorni_caro_consecutivi") or 0
        mancano = max(0, parametri.durata_minima_caro - giorni)
        return {"chiave": CALDO, "icona": "🟠",
                "titolo": f"normale · CALDO da {giorni} {'giorno' if giorni == 1 else 'giorni'}",
                "spiegazione": (f"mercato tirato: niente versamenti straordinari. Il freno scatta a "
                                f"{parametri.durata_minima_caro} giorni di fila"
                                + (f" (ne mancano {mancano})" if mancano else "")
                                + ". Non è un segnale di vendita"),
                "breve": f"niente extra · freno a {parametri.durata_minima_caro} giorni · non vuol dire vendere"}
    if chiave == IN_ARRIVO:
        return {"chiave": IN_ARRIVO, "icona": "🟡",
                "titolo": "normale · STRAORDINARIO IN ARRIVO",
                "spiegazione": (f"il punteggio economico ha passato la soglia oggi: se regge per "
                                f"{parametri.conferma_giorni} giorni di fila scatta lo straordinario. "
                                "Per ora il ricorrente, ma tieni d'occhio i prossimi messaggi"),
                "breve": "soglia economica passata oggi · se regge, domani scatta"}
    icone = {engine.STRAORDINARIO: "🟢", engine.FRENO: "🔴",
             engine.NORMALE: "⚪️", engine.SCONOSCIUTO: "⚠️"}
    return {"chiave": chiave, "icona": icone.get(chiave, ""), "titolo": NOMI_STATO[chiave],
            "spiegazione": SPIEGAZIONE_STATO[chiave], "breve": SPIEGAZIONE_STATO[chiave]}


def _data(giorno):
    return giorno.strftime("%d/%m/%Y") if giorno else "n/d"


def _soldi(valore, valuta="EUR"):
    return f"{valore:,.0f} {valuta}".replace(",", ".")


def _prezzo(valore):
    return f"{valore:,.0f} $".replace(",", ".")


def _num(valore, decimali=2):
    """Numeri all'italiana: virgola decimale, niente zeri finali inutili (3,0x -> 3x)."""
    testo = f"{valore:.{decimali}f}".replace(".", ",")
    if "," in testo:
        testo = testo.rstrip("0").rstrip(",")
    return testo


NOMI_UMANI = {"fng": "il Fear & Greed", "mvrv": "l'MVRV", "mvrv_pct": "il percentile MVRV",
              "mvrv_z": "lo Z-score MVRV", "mayer": "il Mayer multiple", "dd365": "il drawdown annuale",
              "rsi14_d": "l'RSI giornaliero", "rsi14_w": "l'RSI settimanale",
              "price_vs_wma200": "la media a 200 settimane", "pi_ratio": "il Pi Cycle"}


def _nome_umano(chiave):
    return NOMI_UMANI.get(chiave, chiave)


def _del(percentuale):
    """'del 72%' ma 'dell'85%'. Sta in engine.py: qui si riusa, non si riscrive."""
    return engine._del(percentuale)


def _fisso(valore, decimali=2):
    """Come _num ma senza togliere gli zeri: per i punteggi, dove 0,00 e 0,42 vanno allineati."""
    return f"{valore:.{decimali}f}".replace(".", ",")


def riga_dati_breve(foto):
    """Versione compatta per il polso: solo le date, senza spiegazioni."""
    pezzi = [f"dati del {foto['data'].strftime('%d/%m')}"]
    if foto.get("mvrv_data"):
        ritardo = foto.get("mvrv_ritardo_giorni") or 0
        pezzi.append(f"MVRV del {foto['mvrv_data'].strftime('%d/%m')}"
                     + (" (la fonte va di un giorno indietro)" if ritardo == 1 else ""))
    else:
        pezzi.append("MVRV non disponibile")
    if foto.get("ingredienti_mancanti"):
        pezzi.append("manca " + ", ".join(_nome_umano(k) for k in foto["ingredienti_mancanti"]))
    return " · ".join(pezzi)

# ------------------------------------------------------------ avvicinamento

def avvicinamento(ds, indice, giorni=10):
    """Quanto dista il prezzo dalla media a 200 settimane e in che direzione si sta muovendo.

    La direzione si misura sulla distanza, non sul prezzo: quello che conta e' se ci si sta
    avvicinando alla zona o allontanando.
    """
    serie = ds.ind.get("price_vs_wma200") or []
    if indice >= len(serie) or serie[indice] is None:
        return None
    oggi = serie[indice]
    distanza = (oggi - 1.0) * 100.0
    passato = [serie[j] for j in range(max(0, indice - giorni), indice + 1) if serie[j] is not None]
    if len(passato) < 3:
        return {"distanza": distanza, "verso": None, "giorni": 0}
    # da quanti giorni la distanza si muove nella stessa direzione
    verso, conta = None, 0
    for j in range(indice, max(0, indice - 60), -1):
        if serie[j] is None or serie[j - 1] is None:
            break
        passo = serie[j] - serie[j - 1]
        segno = "giu" if passo < 0 else "su"
        if verso is None:
            verso = segno
        if segno != verso:
            break
        conta += 1
    return {"distanza": distanza, "verso": verso, "giorni": conta,
            "variazione": (oggi - passato[0]) * 100.0}


def riga_avvicinamento(ds, indice, valutazione, parametri):
    """Dove sta il prezzo rispetto alla media a 200 settimane, in che direzione, e quanto manca.

    E' la riga che a giugno 2026 sarebbe servita: non "sei arrivato", ma "ti stai avvicinando".
    """
    info = avvicinamento(ds, indice)
    if info is None:
        return "distanza dalla media a 200 settimane non calcolabile"
    if abs(info["distanza"]) < 1:
        pezzo = "in linea con la media a 200 settimane"
    else:
        dove = (f"a +{info['distanza']:.0f}% sopra" if info["distanza"] >= 0
                else f"a {abs(info['distanza']):.0f}% sotto")
        pezzo = f"{dove} la media a 200 settimane"
    if info["verso"] and info["giorni"] >= 3:
        direzione = "in avvicinamento" if info["verso"] == "giu" else "in allontanamento"
        pezzo += f", {direzione} da {info['giorni']} giorni"

    # si parla della soglia PIU' VICINA, non sempre di quella economica (D40)
    chiave = condizione(valutazione, parametri)
    eco = valutazione.get("punteggio_economico")
    caro = valutazione.get("punteggio_caro")
    if chiave == engine.NORMALE and eco is not None and caro is not None:
        verso_eco = eco / parametri.soglia_straordinario if parametri.soglia_straordinario else 0
        verso_caro = caro / parametri.soglia_freno if parametri.soglia_freno else 0
        if verso_eco >= verso_caro:
            pezzo += (f" · economico al {strada(eco, parametri.soglia_straordinario)} della strada "
                      f"verso lo straordinario")
        else:
            pezzo += f" · caro al {strada(caro, parametri.soglia_freno)} della strada verso il caldo"
    elif chiave == engine.FRENO:
        giorni = valutazione.get("giorni_caro_consecutivi")
        if giorni:
            pezzo += f" · mercato caro da {giorni} giorni di fila"
    return pezzo

# ------------------------------------------------------ confronto coi 4 anni

def quanti_piu_alti(ds, chiave, indice, finestra=None, minimo=365):
    """In quanti giorni della finestra dei percentili l'indicatore era piu' alto di oggi (D42).

    E' esattamente il confronto su cui lavora il motore — stessa serie, stessa finestra che finisce
    oggi (quindi niente lookahead), stesso minimo di 365 valori — ma detto con i giorni veri:
    "in 380 giorni su 1.460" invece di "26 giorni su 100", che faceva pensare a cento giorni veri.
    `totale` conta tutti i giorni con un valore nella finestra, oggi compreso.
    """
    serie = ds.ind.get(chiave)
    if not serie or indice >= len(serie) or serie[indice] is None:
        return None
    finestra = finestra or ds.meta.get("finestra_percentile") or 1460
    oggi = serie[indice]
    validi = [x for x in serie[max(0, indice - finestra + 1):indice + 1] if x is not None]
    if len(validi) < max(2, minimo):
        return None
    piu_alti = sum(1 for x in validi if x > oggi)
    uguali = sum(1 for x in validi if x == oggi) - 1          # gli altri giorni identici, oggi escluso
    return {"piu_alti": piu_alti, "uguali": uguali, "totale": len(validi),
            "quota": 100.0 * piu_alti / len(validi), "anni": max(1, round(len(validi) / 365.25))}


def conteggi_del_giorno(ds, indice, chiavi=None):
    """`quanti_piu_alti` per ogni ingrediente: e' quello che serve a `engine.motivi`."""
    return {k: quanti_piu_alti(ds, k, indice) for k in (chiavi or engine.PESI)}


def motivi_del_giorno(ds, indice, valutazione, stato):
    """I motivi del motore riscritti con i giorni veri (D42), piu' le note che aggiunge la regola
    di conferma (per esempio "mercato caro da 16 giorni: sotto i 60 richiesti")."""
    originali = list(valutazione.get("motivi") or [])
    contributi = valutazione.get("contributi")
    if not contributi or stato == engine.SCONOSCIUTO:
        return originali
    valori = {k: ds.ind.get(k, [None] * len(ds))[indice] for k in engine.PESI}
    base = engine.motivi(contributi, stato, valori, conteggi=conteggi_del_giorno(ds, indice, contributi))
    note = [m for m in originali if m.startswith(("mercato caro da", "ingredienti insufficienti"))]
    return base + note

# ------------------------------------------------------------- provenienza

def riga_dati(foto):
    """Quali dati ho usato e di che giorno sono. Sempre presente, in ogni formato (F3.3)."""
    pezzi = [f"prezzo del {_data(foto['data'])} ({foto.get('fonte_prezzo', 'n/d')})"]
    if foto.get("mvrv_data"):
        ritardo = foto.get("mvrv_ritardo_giorni") or 0
        nota = " (ieri: la fonte pubblica con un giorno di ritardo)" if ritardo == 1 else (
            f" ({ritardo} giorni fa)" if ritardo > 1 else "")
        pezzi.append(f"MVRV del {_data(foto['mvrv_data'])}{nota}")
    else:
        pezzi.append("MVRV non disponibile")
    if foto.get("ingredienti_mancanti"):
        pezzi.append("mancano: " + ", ".join(_nome_umano(k) for k in foto["ingredienti_mancanti"]))
    return "Dati usati: " + " · ".join(pezzi) + "."

# -------------------------------------------------------- confronto storico

def episodi(ds, righe, stato=engine.STRAORDINARIO, minimo_giorni=3, parametri=None):
    """Elenco degli episodi passati in una certa condizione: [(inizio, fine, indice_inizio)].

    `stato` puo' essere uno stato del motore o CALDO (che richiede `parametri`).
    """
    fuori, corrente = [], None
    for i in range(len(ds)):
        if stato == CALDO:
            dentro = parametri is not None and condizione(righe[i], parametri) == CALDO
        else:
            dentro = righe[i].get("stato_confermato") == stato
        if dentro:
            corrente = corrente or [ds.dates[i], ds.dates[i], i]
            corrente[1] = ds.dates[i]
        elif corrente:
            if (corrente[1] - corrente[0]).days + 1 >= minimo_giorni:
                fuori.append(tuple(corrente))
            corrente = None
    if corrente and (corrente[1] - corrente[0]).days + 1 >= minimo_giorni:
        fuori.append(tuple(corrente))
    return fuori


def confronto_storico(ds, righe, indice, stato=engine.STRAORDINARIO, parametri=None):
    """L'episodio comparabile PIU' RECENTE e cosa e' successo dopo (D30).

    Non la mediana di tutta la storia: i cicli si stanno accorciando e il premio con essi
    (docs/04 §8), quindi citare la media del 2011-2015 sarebbe promettere un mondo che non c'e' piu'.
    """
    if stato in (engine.NORMALE, engine.SCONOSCIUTO):
        # normale vale l'83% dei giorni: "l'ultima volta normale" non e' un precedente utile (D40)
        return None
    if stato == IN_ARRIVO:
        stato = engine.STRAORDINARIO
    oggi = ds.dates[indice]
    passati = [e for e in episodi(ds, righe, stato, parametri=parametri)
               if e[1] < oggi - datetime.timedelta(days=30)]
    if not passati:
        return None
    inizio, fine, i0 = passati[-1]
    prezzo_allora = ds.prezzi[i0]
    esiti = {}
    for mesi, giorni in (("6 mesi", 182), ("12 mesi", 365)):
        if i0 + giorni < len(ds):
            esiti[mesi] = (ds.prezzi[i0 + giorni] / prezzo_allora - 1) * 100
    return {"inizio": inizio, "fine": fine, "prezzo": prezzo_allora, "esiti": esiti,
            "giorni": (fine - inizio).days + 1}


def riga_confronto(confronto, stato):
    if not confronto:
        return None
    pezzi = [f"L'ultima fase simile è cominciata il {_data(confronto['inizio'])} "
             f"({confronto['giorni']} giorni, prezzo {_prezzo(confronto['prezzo'])})"]
    if confronto["esiti"]:
        dopo = ", ".join(f"dopo {k} {v:+.0f}%" for k, v in confronto["esiti"].items())
        pezzi.append(f"da lì: {dopo}")
    else:
        pezzi.append("non è ancora passato abbastanza tempo per dire com'è andata")
    coda = ("Un solo precedente recente non è una previsione, e l'ampiezza dei cicli si sta "
            "riducendo." if stato == engine.STRAORDINARIO else "Un solo precedente non è una previsione.")
    return " — ".join(pezzi) + ". " + coda

# ------------------------------------------------------------- sforzo

def riga_sforzo(valutazione, budget_mensile, tetto_mesi=None, speso_mesi=0.0, parametri=None):
    """Da moltiplicatore a euro, col saldo del tetto se e' stato deciso (F2.5)."""
    p = parametri or engine.Parametri()
    m = valutazione.get("moltiplicatore")
    if not m:
        return None
    extra_settimana = (m - 1.0) * budget_mensile / 4.0
    testo = (f"Sforzo suggerito: settimana da {_num(m, 1)}x, cioè circa {_soldi(extra_settimana)} in più "
             f"del ricorrente, da mettere in almeno {p.colpi_minimi} colpi e mai in uno solo")
    if tetto_mesi is None:
        testo += (". Tetto del ciclo: non l'hai ancora deciso, quindi non tengo un saldo e non "
                  "propongo tranche oltre questa")
    else:
        residuo = engine.tranche_consentita(valutazione["punteggio_economico"], speso_mesi,
                                            tetto_mesi, p)
        testo += (f". Tetto del ciclo: usati {speso_mesi:.1f} di {tetto_mesi:.0f} mesi equivalenti, "
                  f"disponibili adesso {max(0.0, residuo or 0.0):.1f}")
    return testo + "."

# ------------------------------------------------------------- i formati

def polso(ds, righe, indice, foto, parametri, budget_mensile=200.0):
    """Due o tre righe, tutti i giorni. Non chiede attenzione: la tiene allenata."""
    valutazione = righe[indice]
    stato = valutazione.get("stato_confermato", valutazione["stato"])
    vista = vista_stato(valutazione, parametri)
    testa = (f"{vista['icona']} <b>{_prezzo(foto['prezzo'])}</b> · <b>{vista['titolo']}</b> — "
             f"{vista['breve']}")
    seconda = riga_avvicinamento(ds, indice, valutazione, parametri).capitalize()
    if stato == engine.STRAORDINARIO and valutazione.get("moltiplicatore"):
        m = valutazione["moltiplicatore"]
        extra = (m - 1.0) * budget_mensile / 4.0
        seconda += f" · settimana da {_num(m, 1)}x (~{_soldi(extra)} in più, in più colpi)"
    return f"{testa}\n{seconda} · <i>{riga_dati_breve(foto)}</i>."


def cambio_stato(ds, righe, indice, foto, parametri, precedente, budget_mensile=200.0,
                 tetto_mesi=None, speso_mesi=0.0):
    """Il messaggio che chiede davvero attenzione: si manda solo quando lo stato cambia."""
    valutazione = righe[indice]
    stato = valutazione.get("stato_confermato", valutazione["stato"])
    vista = vista_stato(valutazione, parametri)
    parti = [f"Cambio di stato: da {NOMI_STATO.get(precedente, precedente)} a {NOMI_STATO[stato]}"
             f" ({_data(foto['data'])})",
             f"Cosa vuol dire: {vista['spiegazione']}.",
             f"BTC {_prezzo(foto['prezzo'])} · {riga_avvicinamento(ds, indice, valutazione, parametri)}."]
    motivi = motivi_del_giorno(ds, indice, valutazione, stato)
    if motivi:
        parti.append("Perché: " + "; ".join(motivi) + ".")
    sforzo = riga_sforzo(valutazione, budget_mensile, tetto_mesi, speso_mesi, parametri)
    if sforzo:
        parti.append(sforzo)
    if stato == engine.STRAORDINARIO:
        parti.append(f"Da tenere presente: questa fase può durare e peggiorare — {FATTO_2022}. "
                     "Per questo lo sforzo va spalmato.")
    if stato == engine.FRENO:
        parti.append("Nota: «freno» vuol dire solo non aggiungere extra. Non è un invito a "
                     "vendere, e su 4 massimi storici questo segnale ne ha colti 2.")
    confronto = riga_confronto(confronto_storico(ds, righe, indice, vista["chiave"], parametri),
                               vista["chiave"])
    if confronto:
        parti.append(confronto)
    parti.append(riga_dati(foto))
    return "\n\n".join(parti)


# Massimi di MVRV ai massimi di ciclo (docs/02 §2): servono a dare la scala di quanto sia
# calato il "caro" di ciclo in ciclo, invece di far credere che 4,43 possa tornare.
MVRV_AI_MASSIMI = "4,43 (dic 2017) · 3,43 (apr 2021) · 2,85 (nov 2021) · 2,29 (ott 2025)"
TRENDS_AI_MASSIMI = "100 (dic 2017) · 51 (apr 2021) · 34 (nov 2021) · 32 (ott 2025)"
MVRV_AI_MASSIMI_CORTO = "4,43 · 3,43 · 2,85 · <b>2,29</b> (2017 → 2025)"
TRENDS_AI_MASSIMI_CORTO = "100 · 51 · 34 · <b>32</b> (2017 → 2025)"


def variazione(ds, indice, giorni):
    """Variazione percentuale del prezzo rispetto a `giorni` fa (None se non c'e' storia)."""
    if indice - giorni < 0:
        return None
    prima = ds.prezzi[indice - giorni]
    return (ds.prezzi[indice] / prima - 1) * 100 if prima else None


def _segno(valore, decimali=1):
    return "n/d" if valore is None else f"{valore:+.{decimali}f}%".replace(".", ",")


def _colorato(valore, decimali=1):
    """Variazione di mercato con la pallina del colore giusto.

    Telegram non sa colorare il testo (i tag sono solo b/i/u/s/code): il colore lo fanno le emoji.
    Si colorano SOLO le variazioni di prezzo: la distanza dal massimo o dalla media resta neutra,
    perche' per chi accumula un prezzo piu' basso non e' una cattiva notizia e una pallina rossa
    allenerebbe l'occhio al riflesso sbagliato.
    """
    if valore is None:
        return "n/d"
    pallina = "🟢" if valore > 0 else ("🔴" if valore < 0 else "⚪️")
    return f"{pallina} {_segno(valore, decimali)}"


SEPARATORE = "━━━━━━━━━━━━━━━"


def _nota_ath(ds, indice, massimo_12m, quando_12m):
    """Chiarisce se il massimo dei 12 mesi e' anche quello di sempre, o quanto dista."""
    ath, quando_ath = massimo_storico(ds, indice)
    if abs(ath - massimo_12m) < 1e-6 and quando_ath == quando_12m:
        return " — è anche il massimo storico"
    return (f" · massimo storico {_prezzo(ath)} del {_data(quando_ath)}, "
            f"da lì {_fisso((ds.prezzi[indice] / ath - 1) * 100, 1)}%")


def _punteggio(valore):
    """Un punteggio non si arrotonda a 0,00: 0,005 e 0,000 sono cose diverse e vanno viste."""
    if valore is None:
        return "n/d"
    decimali = 3 if 0 < abs(valore) < 0.1 else 2
    return f"{valore:.{decimali}f}".replace(".", ",")


def strada(valore, soglia):
    """Quanta strada c'è ancora: '3% della strada' si capisce, '0,01' no."""
    if valore is None or not soglia:
        return "n/d"
    return f"{min(100, round(100 * valore / soglia))}%"


def barra(valore, soglia, caselle=5):
    """Barretta di riempimento: quanto siamo vicini alla soglia che fa scattare lo stato."""
    if valore is None or not soglia:
        return "▯" * caselle
    piene = max(0, min(caselle, round(caselle * valore / soglia)))
    return "▮" * piene + "▯" * (caselle - piene)


def chi_contribuisce(valutazione, verso, quanti=3):
    """Quali indicatori stanno spingendo il punteggio, detti per nome. Vuoto = nessuno."""
    contributi = valutazione.get("contributi") or {}
    attivi = [(chiave, c) for chiave, c in contributi.items() if c.get(verso, 0) > 0]
    if not attivi:
        return None
    attivi.sort(key=lambda kv: kv[1][verso] * kv[1]["peso"], reverse=True)
    nomi = [engine.ETICHETTE.get(chiave, chiave).replace("&", "&amp;") for chiave, _ in attivi[:quanti]]
    resto = len(attivi) - len(nomi)
    coda = " e un altro" if resto == 1 else (f" e altri {resto}" if resto > 1 else "")
    testo = ", ".join(nomi) + coda
    return testo


def massimo_storico(ds, indice):
    """Massimo di sempre fino a oggi (per distinguerlo dal massimo degli ultimi 12 mesi)."""
    prezzi = ds.prezzi[:indice + 1]
    valore = max(prezzi)
    return valore, ds.dates[prezzi.index(valore)]


def massimo_annuale(ds, indice, finestra=365):
    inizio = max(0, indice - finestra + 1)
    prezzi = ds.prezzi[inizio:indice + 1]
    massimo = max(prezzi)
    quando = ds.dates[inizio + prezzi.index(massimo)]
    return massimo, quando


ORDINE_ANALISI = (
    ("price_vs_wma200", "prezzo / media 200 settimane", "{:.2f}"),
    ("mayer", "Mayer multiple (prezzo / media 200 giorni)", "{:.2f}"),
    ("dd365", "distanza dal massimo dell'ultimo anno", "{:+.0f}%"),
    ("rsi14_d", "RSI giornaliero", "{:.0f}"),
    ("rsi14_w", "RSI settimanale", "{:.0f}"),
    ("mvrv", "MVRV", "{:.2f}"),
    ("fng", "Fear & Greed", "{:.0f}"),
)


def analisi_completa(ds, righe, indice, foto, parametri, budget_mensile=200.0,
                     tetto_mesi=None, speso_mesi=0.0, limite=4000):
    """Tutto quello che il bot sa oggi, in un solo messaggio Telegram, formattato in HTML.

    Criterio di impaginazione (sessione 12, dopo averlo letto sul telefono): righe corte, una
    informazione per riga, il numero prima e il commento dopo. Le spiegazioni lunghe vanno nella
    guida (`guida()`), non dentro il report di ogni giorno.
    """
    valutazione = righe[indice]
    stato = valutazione.get("stato_confermato", valutazione["stato"])
    v = lambda chiave: ds.ind.get(chiave, [None] * len(ds))[indice]
    pct = lambda chiave: (ds.ind.get(f"pct_{chiave}") or [None] * len(ds))[indice]

    def posizione(chiave):
        """'negli ultimi 4 anni è stato più alto di oggi in 380 giorni su 1.460 (26%)' (D42).

        Giorni veri e verso unico. Se l'ingrediente conta nel punteggio lo si dice, con le stesse
        parole di "spingono:", cosi' la riga e il punteggio non si contraddicono mai.
        """
        conto = quanti_piu_alti(ds, chiave, indice)
        if conto is None:
            return None
        testo = "↳ " + engine.confronto_in_giorni(conto["piu_alti"], conto["totale"], conto["anni"],
                                                  conto["uguali"])
        c = (valutazione.get("contributi") or {}).get(chiave) or {}
        if c.get("caro", 0) > 0:
            testo += " · zona cara"
        elif c.get("economico", 0) > 0:
            testo += " · zona economica"
        return testo

    vista = vista_stato(valutazione, parametri)
    parti = [f"₿ <b>AphroditeBTC</b> · analisi del {_data(foto['data'])}"]

    # --- stato
    blocco = [f"{vista['icona']} <b>{vista['titolo'].upper()}</b>",
              f"<i>{vista['spiegazione']}</i>"]
    if valutazione["punteggio_economico"] is not None:
        eco, caro_p = valutazione["punteggio_economico"], valutazione["punteggio_caro"]
        blocco.append(f"▸ quanto è ECONOMICO  {barra(eco, parametri.soglia_straordinario)}  "
                      f"<b>{strada(eco, parametri.soglia_straordinario)} della strada</b>"
                      f" <i>({_punteggio(eco)} su {_fisso(parametri.soglia_straordinario)} → straordinario)</i>")
        spinta = chi_contribuisce(valutazione, "economico")
        blocco.append(f"     <i>{('spingono: ' + spinta) if spinta else 'nessuno dei 7 indicatori è in zona economica'}</i>")
        blocco.append(f"▸ quanto è CARO       {barra(caro_p, parametri.soglia_freno)}  "
                      f"<b>{strada(caro_p, parametri.soglia_freno)} della strada</b>"
                      f" <i>({_punteggio(caro_p)} su {_fisso(parametri.soglia_freno)} → caldo)</i>")
        spinta = chi_contribuisce(valutazione, "caro")
        blocco.append(f"     <i>{('spingono: ' + spinta) if spinta else 'nessuno dei 7 indicatori è in zona cara'}</i>")
    parti.append("\n".join(blocco))

    # --- prezzo
    massimo, quando = massimo_annuale(ds, indice)
    blocco = [f"💵 <b>PREZZO</b>  <b>{_prezzo(foto['prezzo'])}</b>",
              f"{_colorato(variazione(ds, indice, 1))} 24h   "
              f"{_colorato(variazione(ds, indice, 7))} 7g   "
              f"{_colorato(variazione(ds, indice, 30))} 30g",
              f"▸ dal massimo degli ultimi 12 mesi <b>{_fisso(v('dd365'), 1)}%</b>",
              f"     <i>{_prezzo(massimo)} il {_data(quando)}{_nota_ath(ds, indice, massimo, quando)}</i>"]
    if v("mayer") is not None:
        blocco.append(f"▸ Mayer (media 200 giorni) <b>{_fisso(v('mayer'))}</b>")
        if posizione("mayer"):
            blocco.append(f"     <i>{posizione('mayer')}</i>")
    if v("price_vs_wma200") is not None:
        distanza = (v("price_vs_wma200") - 1) * 100
        blocco.append(f"▸ media 200 settimane <b>{'+' if distanza >= 0 else ''}"
                      f"{_fisso(distanza, 0)}%</b>")
        if posizione("price_vs_wma200"):
            blocco.append(f"     <i>{posizione('price_vs_wma200')}</i>")
    parti.append("\n".join(blocco))

    # --- on-chain
    if v("mvrv") is not None:
        blocco = [f"⛓ <b>MVRV</b>  <b>{_fisso(v('mvrv'))}</b>"]
        if posizione("mvrv"):
            blocco.append(f"     <i>{posizione('mvrv')}</i>")
        blocco.append(f"▸ ai massimi passati {MVRV_AI_MASSIMI_CORTO}")
        ritardo = foto.get("mvrv_ritardo_giorni") or 0
        blocco.append(f"▸ dato del {_data(foto.get('mvrv_data'))}"
                      + (" <i>(la fonte va un giorno indietro)</i>" if ritardo >= 1 else ""))
        parti.append("\n".join(blocco))

    # --- momentum
    blocco = ["📈 <b>MOMENTUM</b>"]
    if v("rsi14_d") is not None:
        blocco.append(f"▸ RSI <b>{_fisso(v('rsi14_w'), 0)}</b> settimana "
                      f"· {_fisso(v('rsi14_d'), 0)} giorno")
        blocco.append("     <i>sotto 30 venduto · sopra 70 comprato</i>")
    if v("pi_ratio") is not None:
        blocco.append(f"▸ Pi Cycle {_fisso(v('pi_ratio'))} <i>(spara a 1,00)</i>")
    if len(blocco) > 1:
        parti.append("\n".join(blocco))

    # --- sentiment
    blocco = ["👥 <b>ATTENZIONE DELLA GENTE</b>"]
    if v("fng") is not None:
        ieri = ds.ind.get("fng", [None] * len(ds))[indice - 1] if indice else None
        delta = f" <i>({_segno(v('fng') - ieri, 0).replace('%','')} vs ieri)</i>" if ieri is not None else ""
        blocco.append(f"▸ Fear &amp; Greed <b>{_fisso(v('fng'), 0)}</b>/100{delta}")
    if v("trends") is not None:
        blocco.append(f"▸ ricerche Google <b>{_fisso(v('trends'), 0)}</b>/100 <i>(mensile)</i>")
        blocco.append(f"     <i>ai massimi passati {TRENDS_AI_MASSIMI_CORTO}</i>")
    if len(blocco) > 1:
        parti.append("\n".join(blocco))

    # --- sforzo e onesta'
    sforzo = riga_sforzo(valutazione, budget_mensile, tetto_mesi, speso_mesi, parametri)
    if sforzo:
        parti.append("💶 <b>COSA VARREBBE FARE</b>\n• " + sforzo.replace(". ", ".\n• "))
    if stato == engine.STRAORDINARIO:
        parti.append("⚠️ <b>ONESTÀ</b>\n• questa fase può durare e peggiorare\n"
                     f"   ↳ {FATTO_2022}")
    confronto = confronto_storico(ds, righe, indice, vista["chiave"], parametri)
    if confronto:
        blocco = ["🕐 <b>L'ULTIMA VOLTA COSÌ</b>",
                  f"▸ {_data(confronto['inizio'])} · {confronto['giorni']} giorni · "
                  f"{_prezzo(confronto['prezzo'])}"]
        if confronto["esiti"]:
            blocco.append("     " + " · ".join(f"{k} <b>{v_:+.0f}%</b>"
                                               for k, v_ in confronto["esiti"].items()))
        else:
            blocco.append("     <i>troppo presto per dire com'è andata</i>")
        blocco.append("<i>Un solo precedente non è una previsione.</i>")
        parti.append("\n".join(blocco))

    parti.append(SEPARATORE + "\n📄 <i>" + riga_dati(foto) + "</i>")
    testo = "\n\n".join(parti)
    if len(testo) > limite:                      # non deve mai spezzarsi in due messaggi
        testo = testo[:limite - 3].rstrip() + "..."
    return testo


GUIDA = """₿ <b>AphroditeBTC — come si legge</b>
<i>Love the asset. Analyze the market.</i>

🧭 <b>LO STATO è la sola cosa che conta</b>
🟢 <b>straordinario</b> — fase rara ed economica: vale versare più del solito, spalmato in più settimane.
⚪️ <b>normale</b> — nessun estremo: i 200 €/mese e basta.
🔴 <b>freno</b> — mercato caro da mesi: nessun versamento extra. <b>Non</b> vuol dire vendere.
🟠 <b>caldo</b> — non è un quarto stato, è un avviso dentro «normale»: il punteggio caro ha passato la soglia ma non da abbastanza tempo per il freno. Niente versamenti extra. Ai due massimi più recenti (nov 2021, ott 2025) era acceso; ma lo era anche a dicembre 2020, prima che il prezzo triplicasse. Per questo non è mai un invito a vendere.
Tutto il resto del messaggio serve solo a spiegare <i>perché</i> siamo in quello stato.

🔢 <b>«PIÙ ALTO DI OGGI IN 386 GIORNI SU 1.460» — cosa vuol dire</b>
Gli ultimi 4 anni sono 1.460 giorni. Per ogni indicatore conto in quanti di quei giorni era più alto di oggi. Esempio vero del 21/09/2026: il Mayer era a 1,23 ed era stato più alto solo in 386 giorni su 1.460 (26%), cioè oggi è più caro di tre giorni su quattro. L'MVRV a 1,62 era stato più alto in 777 giorni su 1.460 (53%): giusto a metà.
La regola è la stessa in tutte le righe: <b>pochi giorni più alti = oggi è caro · tanti giorni più alti = oggi è a sconto</b>. Sotto il 30% l'indicatore entra nel punteggio caro e accanto trovi «zona cara»; sopra il 70% entra in quello economico e trovi «zona economica».
Uso questo e non soglie fisse perché i valori assoluti invecchiano: l'MVRV ai massimi è passato da 4,43 (2017) a 2,29 (2025).

📐 <b>I DUE PUNTEGGI</b>
Sono due termometri separati, non una scala da 0 a 10.
• <b>quanto è ECONOMICO</b>: quanto sono estremi, <i>verso il basso</i>, i sette indicatori. Vale 0 quando nessuno di loro è nel suo 30% più economico degli ultimi 4 anni. A <b>0,43</b> scatta lo stato 🟢.
• <b>quanto è CARO</b>: la stessa cosa verso l'alto. A <b>0,23</b> si accende l'avviso 🟠 caldo; se dura 60 giorni di fila, scatta il 🔴.
Li scrivo come «<b>quanta strada</b>»: 0% = fermo, 100% = lo stato scatta. Sotto trovi <i>quali</i> indicatori stanno spingendo.
Esempio vero del 21/09/2026: ECONOMICO <b>0% della strada</b> (nessuno dei sette è a sconto), CARO <b>32% della strada</b> (spingono RSI giornaliero, Fear &amp; Greed, Mayer e un altro, ma siamo lontani dal caldo). Entrambi bassi = normale, ed è la situazione più frequente.

💵 <b>PREZZO</b>
• <b>Mayer</b> = prezzo / media 200 giorni. Sotto 1 = sotto la media dell'anno; sopra 1,5 storicamente è caro. Ma la soglia invecchia, per questo accanto trovi in quanti giorni degli ultimi 4 anni è stato più alto di oggi.
• <b>Media 200 settimane</b> = il livello che nei mercati orso ha fatto da pavimento… bucato del 34% nel 2022. Vicino o sotto = zona rara.
• <b>dal massimo degli ultimi 12 mesi</b>: quanto siamo sotto il picco dell'ultimo anno — non il massimo storico, che è un'altra cosa e te lo scrivo accanto quando i due non coincidono.

⛓ <b>MVRV</b>
Prezzo di mercato diviso il prezzo medio a cui i bitcoin si sono mossi l'ultima volta. Sotto 1 = in media il mercato è in perdita (storicamente i minimi). Sopra 3 = euforia, ma quel numero si abbassa a ogni ciclo: 4,43 nel 2017, 2,29 nel 2025. Per questo conta il confronto coi 4 anni, non il valore assoluto.

📈 <b>MOMENTUM</b>
• <b>RSI</b> 0-100: sotto 30 = venduto, sopra 70 = comprato. Il settimanale conta più del giornaliero.
• <b>Pi Cycle</b>: vale 1,00 quando spara. Ha centrato i massimi 2013, 2017 e 2021 e ha mancato gli ultimi due: lo mostro come curiosità, non come allarme.

👥 <b>ATTENZIONE DELLA GENTE</b>
• <b>Fear &amp; Greed</b> 0-100: paura estrema sotto 20, avidità sopra 75.
• <b>Ricerche Google</b>: quanto è affollato il mercato. Sotto 10 i 12 mesi dopo sono stati ottimi, sopra 35 pessimi. Ma il picco di ricerche arriva quasi un anno prima del massimo di prezzo: non è un allarme.

🕐 <b>PRECEDENTE PIÙ RECENTE</b>
L'ultima volta in una fase simile, e cosa è successo dopo 6 e 12 mesi. Un caso solo non è una previsione: serve a ricordare che queste fasi esistono e finiscono.

⚠️ <b>DA TENERE A MENTE</b>
• Io non compro e non vendo, e non ti dirò mai di vendere.
• Una fase economica può durare mesi e peggiorare: nel 2022 sono stati 177 giorni sotto la media a 200 settimane, fino a −34%.
• L'ampiezza dei cicli si riduce: stesso segnale, premio più piccolo di una volta.
• Se un dato manca, te lo dico. Non invento numeri."""


def guida():
    """Il messaggio da fissare in chat: cosa vuol dire ogni riga del report."""
    return GUIDA
