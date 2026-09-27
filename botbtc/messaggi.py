"""Il testo dei messaggi (F3 del piano) — da numeri a frasi in italiano.

Tre formati (D19):
- **polso**: poche righe corte, una idea per riga (D48), tutti i giorni, silenzioso. E' la rete di sicurezza per gli ingressi
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
# (fonte: docs/02 §5 — il riferimento resta qui, non nel messaggio: a chi legge su Telegram non serve)
FATTO_2022 = ("nel 2022 il prezzo è rimasto 177 giorni sotto la media a 200 settimane, "
              "fino a -34%")

# I nomi delle fasi, uguali in tutti i messaggi (D49): maiuscola iniziale, mai tutto maiuscolo.
NOMI_STATO = {
    engine.STRAORDINARIO: "Straordinario",
    engine.NORMALE: "Normale",
    engine.FRENO: "Freno",
    engine.SCONOSCIUTO: "Dati incompleti",
}

ICONE_STATO = {engine.STRAORDINARIO: "🟢", engine.FRENO: "🔴", engine.NORMALE: "⚪️", engine.SCONOSCIUTO: "⚠️"}

SPIEGAZIONE_STATO = {
    engine.STRAORDINARIO: "prezzi bassi come capita di rado: vale la pena versare più del solito, in più volte",
    engine.NORMALE: "niente di speciale: bastano i soliti versamenti",
    engine.FRENO: "mercato caro da mesi: niente versamenti extra (non è un invito a vendere)",
    engine.SCONOSCIUTO: "mi mancano dati per dire in che fase siamo",
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
    """Icona, nome e spiegazione della fase da mostrare in testa a ogni messaggio."""
    chiave = condizione(valutazione, parametri)
    if chiave == CALDO:
        giorni = valutazione.get("giorni_caro_consecutivi") or 0
        mancano = max(0, parametri.durata_minima_caro - giorni)
        return {"chiave": CALDO, "icona": "🟠", "titolo": "Caldo",
                "spiegazione": (f"prezzi alti rispetto agli ultimi 4 anni, da {_giorni(giorni)}: niente "
                                f"versamenti extra. Se dura {parametri.durata_minima_caro} giorni di fila "
                                "diventa Freno" + (f" (ne mancano {mancano})" if mancano else "")
                                + ". Non è un segnale di vendita")}
    if chiave == IN_ARRIVO:
        return {"chiave": IN_ARRIVO, "icona": "🟡", "titolo": "Straordinario in arrivo",
                "spiegazione": (f"oggi i prezzi sono entrati in zona sconto: se ci restano "
                                f"{parametri.conferma_giorni} giorni di fila diventa Straordinario. "
                                "Per ora i soliti versamenti")}
    return {"chiave": chiave, "icona": ICONE_STATO.get(chiave, ""), "titolo": NOMI_STATO[chiave],
            "spiegazione": SPIEGAZIONE_STATO[chiave]}


def titolo_fase(valutazione, parametri):
    """'⚪️ <b>Normale</b>': come si scrive la fase in testa a ogni messaggio."""
    vista = vista_stato(valutazione, parametri)
    return f"{vista['icona']} <b>{vista['titolo']}</b>"


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
    """L'episodio precedente in poche righe da Telegram: quando, quanto è durato, cosa è successo dopo."""
    if not confronto:
        return None
    righe = ["🕐 <b>L'ultima volta così</b>",
             f"▸ Cominciata il {_data(confronto['inizio'])} a {_prezzo(confronto['prezzo'])}, "
             f"durata {_giorni(confronto['giorni'])}"]
    if confronto["esiti"]:
        dopo = " · ".join(f"dopo {k} <b>{v:+.0f}%</b>" for k, v in confronto["esiti"].items())
        righe.append(f"▸ Il prezzo da lì: {dopo}")
    else:
        righe.append("▸ È troppo presto per dire com'è andata")
    coda = ("Un solo precedente non è una previsione, e l'ampiezza dei cicli si sta riducendo."
            if stato in (engine.STRAORDINARIO, IN_ARRIVO) else "Un solo precedente non è una previsione.")
    righe.append(f"<i>{coda}</i>")
    return "\n".join(righe)

# ------------------------------------------------------------- sforzo

def riga_sforzo(valutazione, budget_mensile, tetto_mesi=None, speso_mesi=0.0, parametri=None):
    """Da moltiplicatore a euro, col saldo del tetto se è stato deciso (F2.5). Più righe, senza gergo."""
    p = parametri or engine.Parametri()
    m = valutazione.get("moltiplicatore")
    if not m:
        return None
    extra_settimana = (m - 1.0) * budget_mensile / 4.0
    righe = [f"▸ Questa settimana un extra di circa <b>{_euro(extra_settimana)}</b> "
             f"({_num(m, 1)} volte il versamento normale)",
             f"▸ Divisi in almeno {p.colpi_minimi} volte, mai tutti insieme"]
    if tetto_mesi is None:
        righe.append("▸ Il tetto per questa fase non l'hai ancora deciso: per ora non tengo il conto "
                      "di quanto hai messo in più")
    else:
        residuo = engine.tranche_consentita(valutazione["punteggio_economico"], speso_mesi,
                                            tetto_mesi, p)
        righe.append(f"▸ Tetto della fase: usati {_num(speso_mesi, 1)} di {tetto_mesi:.0f} mesi di budget, "
                     f"disponibili adesso {_num(max(0.0, residuo or 0.0), 1)}")
    return "\n".join(righe)

# ------------------------------------------------------------- i formati

def _euro(valore):
    return f"{valore:,.0f} €".replace(",", ".")


def _giorni(n):
    return f"{n} {'giorno' if n == 1 else 'giorni'}"


def riga_media_200(ds, indice):
    """La distanza dalla media a 200 settimane detta come la direbbe una persona (D48)."""
    info = avvicinamento(ds, indice)
    if info is None:
        return "📍 Oggi non riesco a calcolare la distanza dalla media delle ultime 200 settimane."
    d = info["distanza"]
    if abs(d) < 1:
        testo = "📍 Il prezzo è praticamente sulla media delle ultime 200 settimane"
    elif d > 0:
        testo = f"📍 Il prezzo è il {d:.0f}% sopra la media delle ultime 200 settimane"
    else:
        testo = f"📍 Il prezzo è il {abs(d):.0f}% sotto la media delle ultime 200 settimane"
    if info["verso"] and info["giorni"] >= 3:
        g = _giorni(info["giorni"])
        if d >= 1:
            testo += (f", e da {g} ci si sta avvicinando" if info["verso"] == "giu"
                      else f", e da {g} se ne sta allontanando")
        elif d <= -1:
            testo += (f", e da {g} scende ancora più sotto" if info["verso"] == "giu"
                      else f", e da {g} sta risalendo verso la media")
    return testo + "."


def riga_termometro(valutazione, parametri):
    """Quanto è caro o a sconto il mercato, a parole e non in 'percentuali della strada' (D48)."""
    chiave = condizione(valutazione, parametri)
    if chiave == CALDO:
        giorni = valutazione.get("giorni_caro_consecutivi") or 0
        return (f"🌡 Prezzi alti rispetto agli ultimi 4 anni, da {_giorni(giorni)}. "
                "Non è un segnale di vendita: vuol dire solo non aggiungere.")
    if chiave == engine.FRENO:
        giorni = valutazione.get("giorni_caro_consecutivi") or 0
        return (f"🌡 Mercato caro da {_giorni(giorni)} di fila. "
                "Non vuol dire vendere: vuol dire solo non aggiungere.")
    if chiave == IN_ARRIVO:
        return ("🌡 Oggi i prezzi sono entrati in zona sconto. "
                f"Se ci restano {parametri.conferma_giorni} giorni di fila, scatta la fase straordinaria.")
    if chiave == engine.STRAORDINARIO:
        return "🌡 Prezzi bassi come capita di rado. Attenzione: può durare mesi e scendere ancora."
    if chiave == engine.SCONOSCIUTO:
        return "🌡 Mi mancano troppi dati per dire se il mercato è caro o a sconto."
    eco = valutazione.get("punteggio_economico") or 0.0
    caro = valutazione.get("punteggio_caro") or 0.0
    verso_eco = eco / parametri.soglia_straordinario if parametri.soglia_straordinario else 0.0
    verso_caro = caro / parametri.soglia_freno if parametri.soglia_freno else 0.0
    if max(verso_eco, verso_caro) < 0.25:
        return "🌡 Mercato tranquillo: né caro né a sconto."
    if verso_caro > verso_eco:
        if verso_caro < 0.6:
            return "🌡 Un po' caro, ma lontano dagli eccessi."
        return "🌡 Si sta scaldando: siamo vicini alla zona calda."
    if verso_eco < 0.6:
        return "🌡 Prezzi un po' più bassi del solito, ma non è ancora un'occasione."
    return "🌡 Ci stiamo avvicinando alla zona sconto: vale la pena guardare i prossimi giorni."


def riga_soldi(valutazione, parametri, budget_mensile):
    """Cosa fare coi soldi, in una frase. Mai un ordine: il ricorrente, l'extra o niente extra.

    L'importo del versamento mensile non si scrive (richiesta dell'utente, D50): lo conosce. Si scrive
    solo l'extra dello Straordinario, che cambia di settimana in settimana.
    """
    chiave = condizione(valutazione, parametri)
    if chiave == engine.STRAORDINARIO and valutazione.get("moltiplicatore"):
        extra = (valutazione["moltiplicatore"] - 1.0) * budget_mensile / 4.0
        return (f"💶 Oltre al versamento del mese, questa settimana varrebbe un extra di circa "
                f"{_euro(extra)}, diviso in più volte (mai tutto insieme).")
    if chiave == IN_ARRIVO:
        return "💶 Per ora solo il versamento del mese: niente extra finché la fase non si conferma."
    if chiave in (CALDO, engine.FRENO):
        return "💶 Solo il versamento del mese, niente extra."
    if chiave == engine.SCONOSCIUTO:
        return "💶 Nel dubbio, solo il versamento del mese."
    return "💶 Il solito versamento del mese, niente extra."


def riga_date_polso(foto):
    """Di che giorno sono i dati. L'MVRV si nomina a parte solo quando è di un altro giorno."""
    giorno = foto["data"]
    testo = f"Dati del {giorno.strftime('%d/%m')}"
    mvrv = foto.get("mvrv_data")
    if not mvrv:
        testo += " · MVRV non disponibile"
    elif mvrv != giorno:
        testo += f" · MVRV del {mvrv.strftime('%d/%m')} (arriva con un giorno di ritardo)"
    else:
        testo += ", MVRV compreso"
    if foto.get("ingredienti_mancanti"):
        testo += " · manca " + ", ".join(_nome_umano(k) for k in foto["ingredienti_mancanti"])
    return testo


def polso(ds, righe, indice, foto, parametri, budget_mensile=200.0):
    """Il messaggio breve di tutti i giorni (e dei messaggi a sorpresa), scritto per Telegram (D48).

    Quattro righe corte, ognuna con una sola idea: com'è il mercato, cosa fare coi soldi, dove
    sta il prezzo rispetto alla media a 200 settimane (la riga che a giugno 2026 sarebbe servita),
    quanto è caro o a sconto. In fondo le date dei dati.
    """
    valutazione = righe[indice]
    vista = vista_stato(valutazione, parametri)
    righe_testo = [
        f"{vista['icona']} <b>{vista['titolo']}</b> · BTC {_prezzo(foto['prezzo'])}",
        "",
        riga_soldi(valutazione, parametri, budget_mensile),
        riga_media_200(ds, indice),
        riga_termometro(valutazione, parametri),
        "",
        f"<i>{riga_date_polso(foto)} · dettagli con /analisi</i>",
    ]
    return "\n".join(righe_testo)


def cambio_stato(ds, righe, indice, foto, parametri, precedente, budget_mensile=200.0,
                 tetto_mesi=None, speso_mesi=0.0):
    """Il messaggio che chiede davvero attenzione: si manda solo quando la fase cambia."""
    valutazione = righe[indice]
    stato = valutazione.get("stato_confermato", valutazione["stato"])
    vista = vista_stato(valutazione, parametri)
    prima = f"{ICONE_STATO.get(precedente, '')} {NOMI_STATO.get(precedente, precedente)}".strip()
    parti = ["🔔 <b>Cambio di fase</b>\n"
             f"{prima}  →  {vista['icona']} <b>{vista['titolo']}</b>\n"
             f"<i>{vista['spiegazione'][0].upper() + vista['spiegazione'][1:]}.</i>",
             "\n".join([f"💵 <b>BTC {_prezzo(foto['prezzo'])}</b>"]
                       + ([] if valutazione.get("moltiplicatore") and stato == engine.STRAORDINARIO
                          else [riga_soldi(valutazione, parametri, budget_mensile)])   # l'extra ha il suo blocco
                       + [riga_media_200(ds, indice)])]
    motivi = motivi_del_giorno(ds, indice, valutazione, stato)
    if motivi:
        blocco = ["🔎 <b>Perché</b>"]
        for motivo in motivi:
            testa, _, coda = motivo.partition(": ")
            blocco.append(f"▸ {testa[:1].upper() + testa[1:]}" + (f"\n     <i>↳ {coda}</i>" if coda else ""))
        parti.append("\n".join(blocco).replace("&", "&amp;"))
    sforzo = riga_sforzo(valutazione, budget_mensile, tetto_mesi, speso_mesi, parametri)
    if sforzo:
        parti.append("💶 <b>Quanto mettere in più</b>\n" + sforzo)
    if stato == engine.STRAORDINARIO:
        parti.append("⚠️ <b>Da sapere</b>\nQuesta fase può durare e peggiorare: "
                     f"{FATTO_2022}. Per questo l'extra va diviso nel tempo.")
    if stato == engine.FRENO:
        parti.append("⚠️ <b>Da sapere</b>\nFreno vuol dire solo non aggiungere extra: non è un invito a "
                     "vendere. Su 4 massimi storici questo segnale ne ha colti 2.")
    confronto = riga_confronto(confronto_storico(ds, righe, indice, vista["chiave"], parametri),
                               vista["chiave"])
    if confronto:
        parti.append(confronto)
    parti.append(SEPARATORE + "\n<i>📄 " + riga_dati(foto) + "</i>")
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


NOMI_BREVI = {"price_vs_wma200": "media 200 settimane", "mayer": "Mayer", "dd365": "distanza dal massimo",
              "rsi14_w": "RSI settimanale", "rsi14_d": "RSI giornaliero", "mvrv": "MVRV",
              "fng": "Fear & Greed"}


def chi_contribuisce(valutazione, verso, quanti=3):
    """Quali indicatori stanno spingendo il punteggio, detti per nome. Vuoto = nessuno."""
    contributi = valutazione.get("contributi") or {}
    attivi = [(chiave, c) for chiave, c in contributi.items() if c.get(verso, 0) > 0]
    if not attivi:
        return None
    attivi.sort(key=lambda kv: kv[1][verso] * kv[1]["peso"], reverse=True)
    nomi = [NOMI_BREVI.get(chiave, engine.ETICHETTE.get(chiave, chiave)).replace("&", "&amp;")
            for chiave, _ in attivi[:quanti]]
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


def livello(valore, soglia, verso):
    """Il termometro detto a parole: 'lontano dal Caldo', 'a metà strada verso lo Straordinario'..."""
    meta = "lo Straordinario" if verso == "economico" else "il Caldo"
    dal = "dallo Straordinario" if verso == "economico" else "dal Caldo"
    al = "allo Straordinario" if verso == "economico" else "al Caldo"
    if valore is None or not soglia:
        return "non calcolabile"
    quota = valore / soglia
    if quota >= 1:
        return "soglia passata"
    if quota < 0.25:
        return f"lontano {dal}"
    if quota < 0.6:
        return f"a metà strada verso {meta}"
    return f"vicino {al}"


def umore_fng(valore):
    """Le etichette di alternative.me, in italiano."""
    if valore < 25:
        return "paura estrema"
    if valore < 47:
        return "paura"
    if valore <= 54:
        return "neutro"
    if valore <= 75:
        return "avidità"
    return "avidità estrema"


def analisi_completa(ds, righe, indice, foto, parametri, budget_mensile=200.0,
                     tetto_mesi=None, speso_mesi=0.0, limite=4000):
    """Tutto quello che il bot sa oggi, in un solo messaggio Telegram, formattato in HTML.

    Impaginazione (D49): in testa la fase e cosa fare coi soldi, detti come nel messaggio breve;
    poi un blocco per argomento, titolo con emoji, una informazione per riga, il numero in
    grassetto e sotto, in corsivo, il confronto coi 4 anni (la forma approvata in D42). Le
    spiegazioni lunghe stanno nella guida (`guida()`).
    """
    valutazione = righe[indice]
    stato = valutazione.get("stato_confermato", valutazione["stato"])
    v = lambda chiave: ds.ind.get(chiave, [None] * len(ds))[indice]

    def posizione(chiave):
        """'↳ negli ultimi 4 anni è stato più alto di oggi in 380 giorni su 1.460 (26%)' (D42).

        Se l'ingrediente conta nel punteggio lo si dice ("zona cara" / "zona sconto"), con le
        stesse parole del blocco dei termometri, così le due parti non si contraddicono mai.
        """
        conto = quanti_piu_alti(ds, chiave, indice)
        if conto is None:
            return ""
        testo = "↳ " + engine.confronto_in_giorni(conto["piu_alti"], conto["totale"], conto["anni"],
                                                  conto["uguali"])
        c = (valutazione.get("contributi") or {}).get(chiave) or {}
        if c.get("caro", 0) > 0:
            testo += " · <b>zona cara</b>"
        elif c.get("economico", 0) > 0:
            testo += " · <b>zona sconto</b>"
        return f"\n     <i>{testo}</i>"

    vista = vista_stato(valutazione, parametri)
    parti = [f"₿ <b>AphroditeBTC</b> · <i>analisi del {_data(foto['data'])}</i>"]

    # --- la fase, detta come nel messaggio breve
    parti.append("\n".join([f"{vista['icona']} <b>{vista['titolo']}</b> · BTC {_prezzo(foto['prezzo'])}",
                            riga_soldi(valutazione, parametri, budget_mensile),
                            riga_termometro(valutazione, parametri)]))

    # --- i due termometri
    if valutazione["punteggio_economico"] is not None:
        eco, caro_p = valutazione["punteggio_economico"], valutazione["punteggio_caro"]
        blocco = ["📊 <b>I due termometri</b> <i>(pieno = scatta la fase)</i>",
                  f"Sconto {barra(eco, parametri.soglia_straordinario)} "
                  f"{strada(eco, parametri.soglia_straordinario)} · "
                  f"{livello(eco, parametri.soglia_straordinario, 'economico')}",
                  f"Caro {barra(caro_p, parametri.soglia_freno)} "
                  f"{strada(caro_p, parametri.soglia_freno)} · "
                  f"{livello(caro_p, parametri.soglia_freno, 'caro')}"]
        spinta_eco = chi_contribuisce(valutazione, "economico")
        spinta_caro = chi_contribuisce(valutazione, "caro")
        blocco.append(f"<i>In zona sconto: {spinta_eco or 'nessuno dei 7 indicatori'}</i>")
        blocco.append(f"<i>In zona cara: {spinta_caro or 'nessuno dei 7 indicatori'}</i>")
        parti.append("\n".join(blocco))

    # --- prezzo
    massimo, quando = massimo_annuale(ds, indice)
    blocco = [f"💵 <b>Prezzo</b> · <b>{_prezzo(foto['prezzo'])}</b>",
              f"{_colorato(variazione(ds, indice, 1))} in 24 ore · "
              f"{_colorato(variazione(ds, indice, 7))} in 7 giorni · "
              f"{_colorato(variazione(ds, indice, 30))} in 30 giorni",
              f"▸ <b>{_fisso(v('dd365'), 1)}%</b> dal massimo degli ultimi 12 mesi"
              f"\n     <i>{_prezzo(massimo)} il {_data(quando)}{_nota_ath(ds, indice, massimo, quando)}</i>"
              + posizione("dd365")]
    if v("mayer") is not None:
        scarto = (v("mayer") - 1) * 100
        dove = f"{abs(scarto):.0f}% {'sopra' if scarto >= 0 else 'sotto'}"
        blocco.append(f"▸ Mayer <b>{_fisso(v('mayer'))}</b>: il prezzo è il {dove} la media di 200 giorni"
                      + posizione("mayer"))
    if v("price_vs_wma200") is not None:
        scarto = (v("price_vs_wma200") - 1) * 100
        dove = f"{abs(scarto):.0f}% {'sopra' if scarto >= 0 else 'sotto'}"
        blocco.append(f"▸ Media 200 settimane: il prezzo è il <b>{dove}</b>" + posizione("price_vs_wma200"))
    parti.append("\n".join(blocco))

    # --- on-chain
    if v("mvrv") is not None:
        ritardo = foto.get("mvrv_ritardo_giorni") or 0
        blocco = [f"⛓ <b>MVRV</b> · <b>{_fisso(v('mvrv'))}</b>",
                  "<i>valore di mercato ÷ prezzo medio pagato da chi tiene i bitcoin</i>"
                  + posizione("mvrv"),
                  f"▸ Ai massimi passati: {MVRV_AI_MASSIMI_CORTO}",
                  f"▸ Dato del {_data(foto.get('mvrv_data'))}"
                  + (" <i>(la fonte pubblica con un giorno di ritardo)</i>" if ritardo >= 1 else "")]
        parti.append("\n".join(blocco))

    # --- momentum
    blocco = ["📈 <b>Slancio</b>"]
    if v("rsi14_w") is not None:
        blocco.append(f"▸ RSI settimanale <b>{_fisso(v('rsi14_w'), 0)}</b>" + posizione("rsi14_w"))
    if v("rsi14_d") is not None:
        blocco.append(f"▸ RSI giornaliero <b>{_fisso(v('rsi14_d'), 0)}</b>" + posizione("rsi14_d"))
    if v("pi_ratio") is not None:
        blocco.append(f"▸ Pi Cycle <b>{_fisso(v('pi_ratio'))}</b> <i>(scatta a 1,00)</i>")
    if len(blocco) > 1:
        blocco.append("<i>RSI: sotto 30 = molto venduto · sopra 70 = molto comprato</i>")
        parti.append("\n".join(blocco))

    # --- sentiment
    blocco = ["👥 <b>Umore della gente</b>"]
    if v("fng") is not None:
        ieri = ds.ind.get("fng", [None] * len(ds))[indice - 1] if indice else None
        delta = f" <i>(ieri {_fisso(ieri, 0)})</i>" if ieri is not None else ""
        blocco.append(f"▸ Fear &amp; Greed <b>{_fisso(v('fng'), 0)}</b>/100 · {umore_fng(v('fng'))}{delta}"
                      + posizione("fng"))
    if v("trends") is not None:
        blocco.append(f"▸ Ricerche Google <b>{_fisso(v('trends'), 0)}</b>/100 <i>(dato mensile)</i>"
                      f"\n     <i>ai massimi passati {TRENDS_AI_MASSIMI_CORTO}</i>")
    if len(blocco) > 1:
        parti.append("\n".join(blocco))

    # --- sforzo e onestà
    sforzo = riga_sforzo(valutazione, budget_mensile, tetto_mesi, speso_mesi, parametri)
    if sforzo:
        parti.append("💶 <b>Quanto mettere in più</b>\n" + sforzo)
    if stato == engine.STRAORDINARIO:
        parti.append("⚠️ <b>Da sapere</b>\nQuesta fase può durare e peggiorare: "
                     f"{FATTO_2022}.")
    confronto = riga_confronto(confronto_storico(ds, righe, indice, vista["chiave"], parametri),
                               vista["chiave"])
    if confronto:
        parti.append(confronto)

    parti.append(SEPARATORE + "\n<i>📄 " + riga_dati(foto) + "\nCosa vuol dire ogni riga: /guida</i>")
    testo = "\n\n".join(parti)
    if len(testo) > limite:                      # non deve mai spezzarsi in due messaggi
        testo = testo[:limite - 3].rstrip() + "..."
    return testo


GUIDA = """₿ <b>AphroditeBTC — come si legge</b>
<i>Love the asset. Analyze the market.</i>

🧭 <b>Le fasi: è la sola cosa che conta</b>
🟢 <b>Straordinario</b> — prezzi bassi come capita di rado. Vale la pena aggiungere un extra al versamento del mese, diviso in più settimane.
⚪️ <b>Normale</b> — niente di speciale: basta il solito versamento del mese. È la fase più frequente.
🟠 <b>Caldo</b> — prezzi alti rispetto agli ultimi 4 anni: niente extra. Non è un invito a vendere: era acceso ai massimi di nov 2021 e ott 2025, ma anche a dicembre 2020, prima che il prezzo triplicasse.
🔴 <b>Freno</b> — Caldo che dura da 60 giorni di fila: niente extra. Anche qui, <b>non</b> vuol dire vendere.
🟡 <b>Straordinario in arrivo</b> — il primo giorno di sconto: se regge un altro giorno, diventa Straordinario.

📩 <b>Il messaggio breve</b> (ogni mattina e con /stato)
💶 cosa fare coi soldi · 📍 quanto dista il prezzo dalla media delle ultime 200 settimane · 🌡 se il mercato è caro o a sconto, a parole. In fondo, di che giorno sono i dati.

🔢 <b>«Più alto di oggi in 386 giorni su 1.460»</b>
Gli ultimi 4 anni sono 1.460 giorni. Per ogni indicatore conto in quanti di quei giorni era più alto di oggi. Esempio del 21/09/2026: il Mayer era stato più alto in 386 giorni su 1.460 (26%), quindi oggi è più caro di tre giorni su quattro.
<b>Pochi giorni più alti = oggi è caro · tanti = oggi è a sconto.</b> Sotto il 30% l'indicatore finisce in «zona cara», sopra il 70% in «zona sconto».
Uso questo confronto e non soglie fisse perché le soglie invecchiano: l'MVRV ai massimi è sceso da 4,43 (2017) a 2,29 (2025).

📊 <b>I due termometri</b>
Due misure separate. <b>Sconto</b>: quanti indicatori sono in zona sconto e quanto. <b>Caro</b>: lo stesso verso l'alto. La barretta ▮▮▯▯▯ si riempie man mano: piena = scatta la fase (Straordinario per lo sconto, Caldo per il caro). Con /perche vedi quanto pesa ogni indicatore.

💵 <b>Prezzo</b>
• <b>Dal massimo degli ultimi 12 mesi</b>: quanto siamo sotto il picco dell'ultimo anno (se non è anche il record storico, te lo scrivo).
• <b>Mayer</b>: prezzo diviso la media degli ultimi 200 giorni. 1,19 = il 19% sopra.
• <b>Media 200 settimane</b>: nei crolli passati ha fatto da pavimento, ma nel 2022 è stata bucata del 34%. Vicino o sotto = fase rara.

⛓ <b>MVRV</b>
Il valore di mercato diviso il prezzo medio a cui chi tiene i bitcoin li ha pagati. Sotto 1 = in media il mercato è in perdita (storicamente i minimi). Più è alto, più c'è guadagno da incassare.

📈 <b>Slancio</b>
• <b>RSI</b> da 0 a 100: sotto 30 = molto venduto, sopra 70 = molto comprato. Il settimanale conta più del giornaliero.
• <b>Pi Cycle</b>: scatta a 1,00. Ha centrato i massimi 2013, 2017 e 2021 e mancato gli ultimi due: è una curiosità, non un allarme.

👥 <b>Umore della gente</b>
• <b>Fear &amp; Greed</b> da 0 a 100: sotto 25 paura estrema, sopra 75 avidità estrema.
• <b>Ricerche Google</b>: quanta gente cerca «bitcoin». Sotto 10 i 12 mesi dopo sono stati ottimi, sopra 35 pessimi; ma il picco di ricerche arriva quasi un anno prima del massimo di prezzo.

🕐 <b>L'ultima volta così</b>
L'ultima fase simile e cosa ha fatto il prezzo 6 e 12 mesi dopo. Un caso solo non è una previsione.

⚠️ <b>Da tenere a mente</b>
• Non compro e non vendo, e non ti dirò mai di vendere.
• Una fase a sconto può durare mesi e peggiorare: nel 2022 il prezzo è rimasto 177 giorni sotto la media a 200 settimane, fino a −34%.
• Ogni ciclo rende meno del precedente: stesso segnale, premio più piccolo.
• Se un dato manca te lo dico. Non invento numeri."""


def guida():
    """Il messaggio da fissare in chat: cosa vuol dire ogni riga del report."""
    return GUIDA
