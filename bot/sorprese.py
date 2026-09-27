"""Messaggi a sorpresa in settimana (D46): il bot si fa vivo anche quando nessuno gli scrive.

Richiesta dell'utente: in un mercato orso, quando per settimane non succede niente, l'attenzione cala. Il bot
manda il polso di due righe N volte a settimana (default 3), in giorni diversi, a un'ora casuale della fascia
lavorativa (default 10-18, lunedì-venerdì, ora italiana). Tutto modificabile in bot/.env.

Il piano della settimana si estrae una volta e si salva nel database: un riavvio del bot non lo rimescola e non
manda doppioni. Un messaggio il cui orario è passato mentre il bot era spento si manda solo se si è ancora nella
fascia dello stesso giorno; altrimenti si salta, così non arriva mai di sera. Mai più di uno per volta.
Funzioni pure (orologio e caso si passano da fuori): si testano senza aspettare una settimana.
"""

import datetime
import random

CHIAVE = "sorprese_piano"


def adesso(fuso="Europe/Rome"):
    """L'ora dell'utente, senza fuso attaccato.

    Sul VPS (Linux) si usa il fuso dichiarato, qualunque sia l'ora del server. Su Windows il database dei fusi di
    solito manca (zoneinfo senza il pacchetto tzdata): lì si usa l'ora del PC, che è già quella dell'utente.
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(fuso)).replace(tzinfo=None)
    except Exception:
        return datetime.datetime.now()


def settimana_di(momento):
    anno, numero, _ = momento.isocalendar()
    return f"{anno}-W{numero:02d}"


def estrai_piano(momento, quanti, ora_da=10, ora_a=18, solo_feriali=True, rng=None):
    """Gli orari dei messaggi per il resto della settimana di `momento`: solo futuri, in fascia, ordinati.

    Giorni diversi finché bastano; se ne chiedi più dei giorni della settimana, alcuni giorni ne avranno due.
    Se la settimana è già a metà (primo avvio di giovedì) se ne estraggono solo quanti ci stanno nei giorni rimasti.
    """
    rng = rng or random.Random()
    if quanti <= 0 or ora_a <= ora_da:
        return []
    lunedi = momento.date() - datetime.timedelta(days=momento.weekday())
    giorni = [lunedi + datetime.timedelta(days=i) for i in range(5 if solo_feriali else 7)]

    def finestra(giorno):
        inizio, fine = ora_da * 60, ora_a * 60
        if giorno == momento.date():
            inizio = max(inizio, momento.hour * 60 + momento.minute + 5)    # almeno 5 minuti da adesso
        return (inizio, fine) if inizio < fine else None

    liberi = [g for g in giorni if g >= momento.date() and finestra(g)]
    if not liberi:
        return []
    if quanti <= len(giorni):
        scelti = rng.sample(liberi, min(quanti, len(liberi)))
    else:
        scelti = [rng.choice(liberi) for _ in range(quanti)]
    orari = []
    for giorno in scelti:
        inizio, fine = finestra(giorno)
        minuto = rng.randrange(inizio, fine)
        orari.append(datetime.datetime.combine(giorno, datetime.time(minuto // 60, minuto % 60)))
    return sorted(orari)


def aggiorna_piano(piano, momento, quanti, ora_da=10, ora_a=18, solo_feriali=True, rng=None):
    """Ritorna (piano, da_mandare, saltati).

    `piano` è il dizionario salvato nel database ({} la prima volta). Si rifà da capo a ogni settimana nuova o
    se cambiano i parametri nel .env. `da_mandare` ha al massimo un orario: se ne sono scaduti due insieme
    (bot spento a lungo), si manda solo il più recente e gli altri si saltano.
    """
    firma = f"{quanti}|{ora_da}-{ora_a}|{int(solo_feriali)}"
    if not piano or piano.get("settimana") != settimana_di(momento) or piano.get("firma") != firma:
        piano = {"settimana": settimana_di(momento), "firma": firma, "fatti": [],
                 "orari": [o.isoformat(timespec="minutes")
                           for o in estrai_piano(momento, quanti, ora_da, ora_a, solo_feriali, rng)]}
    scaduti = [o for o in piano["orari"]
               if o not in piano["fatti"] and datetime.datetime.fromisoformat(o) <= momento]
    validi = [o for o in scaduti
              if datetime.datetime.fromisoformat(o).date() == momento.date() and momento.hour < ora_a]
    da_mandare = validi[-1:]
    saltati = [o for o in scaduti if o not in da_mandare]
    piano["fatti"] = piano["fatti"] + scaduti
    return piano, da_mandare, saltati
