"""/ai_commentary — il report di oggi raccontato da un modello linguistico (D44).

Prende lo stesso testo di /analisi e lo fa commentare a un modello, in italiano, con lo stile di un pezzo
esplicativo di BBC News: la notizia del giorno in apertura, poi il perché, poi cosa tenere d'occhio. Frasi chiare,
tono sobrio ma umano. Pensato per chi è all'inizio con le cripto: ogni termine tecnico si spiega quando compare.

Un modello linguistico può inventare. Per questo, prima di mandare il commento, due controlli automatici:
1. **ogni numero del commento deve esistere nel materiale che gli abbiamo dato** (report, guida, budget): è la
   regola del progetto "niente numeri a memoria". Sono ammessi gli arrotondamenti ("circa 84 mila dollari");
2. **nessun invito a comprare o vendere, nessun consiglio, nessuna previsione di prezzo** (D16).
Se un controllo fallisce, il modello riceve l'elenco dei problemi e riscrive una volta. Se fallisce ancora il
commento non si manda e il bot dice perché: meglio nessun commento che un commento con un numero inventato.

Solo libreria standard: POST HTTPS con urllib, come per Telegram (D37). Va bene qualunque API compatibile con
OpenAI (.../chat/completions) e quella di Anthropic (.../v1/messages). Chiave, URL e modello stanno in bot/.env.
"""

import html
import json
import re
import urllib.error
import urllib.request

CHIUSURA = "Non è un consiglio finanziario: il bot descrive, le decisioni restano tue."

ISTRUZIONI = """Sei il commentatore di AphroditeBTC, un bot personale che osserva Bitcoin ogni giorno per un risparmiatore che versa una quota fissa ogni mese. Ricevi il report di oggi e lo racconti in italiano.

STILE
- Come un pezzo esplicativo di BBC News: apri con la notizia del giorno in una frase (in che fase è il mercato secondo il bot e cosa significa per chi versa ogni mese), poi il perché, poi cosa tenere d'occhio nei prossimi giorni.
- Chiaro, sobrio, fattuale, ma umano e scorrevole: non burocratico, non rigido, niente enfasi da trader.
- Il lettore è all'inizio con le cripto. Ogni termine tecnico (Mayer multiple, MVRV, RSI, media a 200 settimane, Fear & Greed, gli stati straordinario/normale/freno/caldo) va spiegato in parole semplici la prima volta che compare, in mezza frase.
- Tra 180 e 280 parole, da 3 a 5 paragrafi brevi. Niente titoli, niente elenchi puntati, niente markdown, niente asterischi.

REGOLE CHE NON SI POSSONO VIOLARE
1. Usa solo le informazioni del report e della guida qui sotto. Nessuna notizia, nessun dato, nessun evento esterno.
2. Ogni numero che scrivi deve comparire nel report o nella guida. Copialo com'è, oppure arrotondalo dicendolo ("circa 84 mila dollari"). Non calcolare numeri nuovi (niente differenze, somme o medie tue).
3. Il bot non dà ordini e non fa previsioni. Per i soldi dell'utente usa solo le parole del bot: "versamento", "versare", "quota ricorrente", "versamento straordinario". Non usare mai i verbi comprare, vendere, acquistare, liquidare (unica eccezione: la frase "non vuol dire vendere"). Niente "dovresti", "ti conviene", "è il momento di". Niente futuro sul prezzo ("salirà", "scenderà"): se parli di ipotesi usa il condizionale ("se il prezzo scendesse...").
4. Lo sforzo lo decide il bot: nello stato normale il versamento ricorrente e basta; nello straordinario un versamento in più, spalmato in più colpi; nel freno nessun versamento in più, che non vuol dire vendere; il caldo è un avviso dentro il normale.
5. Se un dato manca o è del giorno prima, dillo come fa il report.
6. Non aggiungere avvertenze finali: le aggiunge il bot."""

RIPROVA = ("Il commento non rispetta le regole: {problemi}. Riscrivilo da capo rispettando tutte le regole: "
           "solo numeri presenti nel report o nella guida (arrotondati solo dicendolo), per i soldi dell'utente "
           "solo 'versamento/versare', nessun consiglio, nessun futuro sul prezzo (usa il condizionale).")


class ErroreModello(Exception):
    """Il modello non ha risposto, o ha risposto in un modo che non sappiamo leggere."""


class RispostaTroncata(ErroreModello):
    """Il modello si è fermato per il limite di lunghezza: il testo è a metà. Trovato alla prima prova vera
    con Gemini 3.8 Flash, che ragiona prima di rispondere e consumava il limite nel ragionamento."""

    def __init__(self, parziale):
        super().__init__("risposta interrotta a metà per il limite di lunghezza")
        self.parziale = parziale


# ------------------------------------------------------------------ materiale

def testo_semplice(testo_html):
    """Dal testo HTML dei messaggi al testo semplice: via i tag, entità decodificate."""
    return html.unescape(re.sub(r"<[^>]+>", "", testo_html or "")).strip()


def materiale(analisi_html, guida_html, budget_mensile):
    """Tutto quello che il modello può usare. È anche la fonte contro cui si controllano i numeri."""
    return ("GUIDA (come si legge il report: serve a spiegare i termini)\n"
            f"{testo_semplice(guida_html)}\n\n"
            f"VERSAMENTO RICORRENTE DELL'UTENTE: {budget_mensile:g} euro al mese.\n\n"
            f"REPORT DI OGGI\n{testo_semplice(analisi_html)}")


# ------------------------------------------------------------ controllo numeri

_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
_MOLTIPLICATORE = re.compile(r"^\s*(miliard\w*|milion\w*|mila|mille|k)\b", re.I)
_FATTORI = {"miliard": 1e9, "milion": 1e6, "mila": 1e3, "mille": 1e3, "k": 1e3}


def _gruppi_da_tre(parte, separatore):
    """Un separatore delle migliaia è credibile solo se dopo di lui ci sono sempre esattamente tre cifre."""
    return all(len(pezzo) == 3 for pezzo in parte.split(separatore)[1:])


def _letture(token):
    """Le letture credibili di un numero scritto, come coppie (valore, decimali).

    Italiana: punto per le migliaia (solo a gruppi di tre cifre), virgola decimale: 84.093 = 84093, 1,57.
    Inglese: virgola per le migliaia (solo a gruppi di tre), punto decimale: 84,093 = 84093, 1.57.
    "2,5" quindi è solo 2,5 e mai 25: all'inglese quella virgola non sarebbe un separatore credibile.
    I decimali dicono quanto è preciso il numero, e quindi quanto si può arrotondare.
    """
    letture = set()
    if token.count(",") <= 1:
        intero, _, decimali = token.partition(",")
        if _gruppi_da_tre(intero, "."):
            letture.add((float(intero.replace(".", "") + ("." + decimali if decimali else "")), len(decimali)))
    if token.count(".") <= 1:
        intero, _, decimali = token.partition(".")
        if _gruppi_da_tre(intero, ","):
            letture.add((float(intero.replace(",", "") + ("." + decimali if decimali else "")), len(decimali)))
    return letture


def _valori_fonte(fonte):
    return {abs(v) for m in _NUMERO.finditer(fonte) for v, _ in _letture(m.group())}


def numeri_inventati(commento, fonte):
    """I numeri del commento che non si ritrovano nella fonte, nemmeno arrotondati.

    Ammessi: i numeri della fonte copiati; gli arrotondamenti (1,6 per 1,57; "84 mila" o "84.000" per
    84.093); gli interi da 0 a 10, che servono a contare ("tre indicatori", "4 anni").
    """
    valori = _valori_fonte(fonte)
    fuori = []
    for m in _NUMERO.finditer(commento):
        token = m.group()
        dopo = _MOLTIPLICATORE.match(commento[m.end():m.end() + 14])
        fattore = _FATTORI[next(k for k in _FATTORI if dopo.group(1).lower().startswith(k))] if dopo else 1.0
        trovato = False
        for valore, decimali in _letture(token):
            x = abs(valore) * fattore
            if fattore == 1.0 and decimali == 0 and x <= 10 and x == int(x):
                trovato = True
                break
            tolleranza = 0.5 * (10 ** -decimali) * fattore
            if fattore == 1.0 and decimali == 0 and x >= 1000:       # 84.000 = arrotondamento di 84.093
                zeri = len(str(int(x))) - len(str(int(x)).rstrip("0"))
                tolleranza = max(tolleranza, 0.5 * 10 ** zeri)
            if any(abs(x - y) <= tolleranza + 1e-9 for y in valori):
                trovato = True
                break
        if not trovato:
            fuori.append(token + (" " + dopo.group(1) if dopo else ""))
    return fuori


# ------------------------------------------------------------ controllo parole

_VERBI_VIETATI = re.compile(r"\b(compra|compri|comprate|comprare|vendi|venda|vendete|vendere|acquista|"
                            r"acquistate|acquistare|liquida|liquidate|liquidare)\b", re.I)
_ECCEZIONE_VENDERE = re.compile(r"non (vuol dire|significa|è un invito a) vendere", re.I)
_CONSIGLI = re.compile(r"\b(dovresti|dovreste|ti conviene|vi conviene|ti consiglio|vi consiglio|"
                       r"è il momento (giusto )?(di|per))\b", re.I)
_PREVISIONI = re.compile(r"\b(salirà|scenderà|crollerà|esploderà|raggiungerà|toccherà|arriverà a)\b", re.I)


def parole_vietate(commento):
    """Inviti a comprare/vendere, consigli e previsioni di prezzo trovati nel commento."""
    pulito = _ECCEZIONE_VENDERE.sub("", commento)
    trovate = []
    for regola, nome in ((_VERBI_VIETATI, "verbi di compravendita"), (_CONSIGLI, "consigli"),
                         (_PREVISIONI, "previsioni di prezzo")):
        parole = sorted({m.group(0).lower() for m in regola.finditer(pulito)})
        if parole:
            trovate.append(f"{nome}: {', '.join(parole)}")
    return trovate


PAROLE_MINIME = 80
_FINE_FRASE = tuple(".!?…»)\"'")


def controlla(commento, fonte):
    """Elenco dei problemi del commento (vuoto = si può mandare)."""
    problemi = []
    parole = len(commento.split())
    if parole < PAROLE_MINIME:
        problemi.append(f"troppo corto ({parole} parole): servono almeno {PAROLE_MINIME} parole, testo completo")
    if not commento.rstrip().endswith(_FINE_FRASE):
        problemi.append("sembra interrotto a metà: l'ultima frase non finisce")
    inventati = numeri_inventati(commento, fonte)
    if inventati:
        problemi.append("numeri che non compaiono nel report: " + ", ".join(inventati))
    problemi += parole_vietate(commento)
    return problemi


# ------------------------------------------------------------------ il modello

def _oscura(testo, chiave):
    return testo.replace(chiave, "***CHIAVE***") if chiave else testo


def chiama_modello(messaggi, url, modello, chiave, timeout=90, _apri=None):
    """Una chiamata al modello. Ritorna il testo della risposta o solleva ErroreModello.

    Formato Anthropic se l'URL è di anthropic.com, altrimenti quello compatibile con OpenAI. Se il servizio
    rifiuta i parametri facoltativi (temperature, max_tokens: alcuni modelli recenti non li accettano),
    riprova una volta con la richiesta minima.
    """
    apri = _apri or urllib.request.urlopen
    anthropic = "anthropic.com" in url
    if anthropic:
        base = {"model": modello, "max_tokens": 8192,
                "system": "\n\n".join(m["content"] for m in messaggi if m["role"] == "system"),
                "messages": [m for m in messaggi if m["role"] != "system"]}
        extra = {"temperature": 0.4}
        intestazioni = {"x-api-key": chiave, "anthropic-version": "2023-06-01",
                        "content-type": "application/json"}
    else:
        base = {"model": modello, "messages": messaggi}
        extra = {"temperature": 0.4, "max_tokens": 8192}
        if "googleapis.com" in url:
            extra["reasoning_effort"] = "low"        # Gemini ragiona prima di rispondere: poco basta
        if "perplexity.ai" in url:
            base["disable_search"] = True            # niente ricerca sul web: solo il nostro report
        intestazioni = {"Authorization": "Bearer " + chiave, "Content-Type": "application/json"}

    ultimo = None
    for corpo in ({**base, **extra}, base):
        richiesta = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),
                                           headers=intestazioni, method="POST")
        try:
            with apri(richiesta, timeout=timeout) as risposta:
                dati = json.loads(risposta.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            dettaglio = _oscura(e.read().decode("utf-8", "ignore")[:300], chiave)
            ultimo = ErroreModello(f"HTTP {e.code}: {dettaglio}")
            if e.code == 400 and corpo is not base:
                continue                             # forse un parametro facoltativo: riprova senza
            raise ultimo
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise ErroreModello(_oscura(f"rete o risposta illeggibile: {e}", chiave))
    else:
        raise ultimo
    try:
        if anthropic:
            testo = "".join(b.get("text", "") for b in dati["content"] if b.get("type") == "text")
            fine = dati.get("stop_reason")
        else:
            testo = dati["choices"][0]["message"]["content"]
            fine = dati["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError):
        raise ErroreModello("risposta in un formato inatteso")
    if fine in ("length", "max_tokens"):
        raise RispostaTroncata(testo or "")
    return testo or ""


def pulisci(testo):
    """Via i ragionamenti interni di alcuni modelli (<think>) e il markdown che Telegram non capirebbe."""
    testo = re.sub(r"<think>.*?</think>", "", testo or "", flags=re.S | re.I)
    testo = re.sub(r"\*\*|__|^#+\s*", "", testo, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", testo).strip()


# ------------------------------------------------------------------ il comando

def commenta(analisi_html, guida_html, budget_mensile, url, modello, chiave, data=None,
             timeout=90, chiama=None):
    """Il commento pronto per Telegram (HTML). Ritorna (ok, testo): con ok False il testo spiega perché."""
    if not (url and modello and chiave):
        mancano = [n for n, v in (("BOTBTC_LLM_URL", url), ("BOTBTC_LLM_MODELLO", modello),
                                  ("la chiave llmapi", chiave)) if not v]
        return False, ("🧠 Il commento AI non è configurato: in <code>bot/.env</code> manca "
                       + ", ".join(mancano) + ".")
    chiama = chiama or (lambda messaggi: chiama_modello(messaggi, url, modello, chiave, timeout))
    fonte = materiale(analisi_html, guida_html, budget_mensile)
    messaggi = [{"role": "system", "content": ISTRUZIONI}, {"role": "user", "content": fonte}]
    problemi = []
    for _tentativo in range(2):
        try:
            bozza = pulisci(chiama(messaggi))
            problemi = controlla(bozza, fonte) if bozza else ["risposta vuota"]
        except RispostaTroncata as e:
            bozza = pulisci(e.parziale)
            problemi = ["risposta interrotta a metà per lunghezza: scrivi un testo completo e più breve"]
        except ErroreModello as e:
            return False, ("🧠 Non riesco a ottenere il commento dal modello "
                           f"(<i>{html.escape(str(e))}</i>). Il report resta disponibile con /analisi.")
        if not problemi:
            giorno = f" del {data.strftime('%d/%m/%Y')}" if data else ""
            corpo = "\n\n".join(html.escape(p.strip(), quote=False) for p in bozza.split("\n\n") if p.strip())
            return True, (f"🧠 <b>AphroditeBTC · il commento di oggi</b>\n"
                          f"<i>Scritto da un modello linguistico a partire dall'analisi{giorno}: "
                          f"ogni numero è stato controllato sul report.</i>\n\n{corpo}\n\n<i>{CHIUSURA}</i>")
        messaggi = messaggi + [{"role": "assistant", "content": bozza or "(vuoto)"},
                               {"role": "user", "content": RIPROVA.format(problemi="; ".join(problemi))}]
    return False, ("🧠 Il commento scritto dal modello non ha passato i controlli, quindi non te lo mando:\n<i>"
                   + html.escape("; ".join(problemi)) + "</i>\nIl report resta disponibile con /analisi.")
