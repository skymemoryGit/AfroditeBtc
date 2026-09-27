"""Configurazione del bot — tutti i parametri in un posto solo.

Regola del progetto: il budget mensile deve poter passare da 200 a 500 o 1000
cambiando un parametro, non il codice. Lo stesso vale per orari, soglie e finestre.

I segreti (token Telegram, chat_id) NON stanno qui: si leggono da variabili
d'ambiente o dal file .env accanto a questo modulo (.env e' in .gitignore).
"""

import os

# --------------------------------------------------------------------- .env

def load_dotenv(path=None):
    """Legge un .env minimale (RIGA = valore) e lo mette in os.environ senza sovrascrivere.

    Nessuna dipendenza esterna: il file e' nostro e il formato lo decidiamo noi.
    Righe vuote e righe che iniziano con # vengono ignorate.
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    return True


def _env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _env_float(name, default):
    v = _env(name)
    return float(v) if v is not None else default


def _env_int(name, default):
    v = _env(name)
    return int(v) if v is not None else default


# Il .env va letto QUI, prima che i parametri qui sotto vengano valutati: leggerlo dopo
# significherebbe avere costanti gia' fissate a None (bug trovato alla prima prova di Telegram,
# che rispondeva 404 perche' l'URL conteneva un token vuoto).
load_dotenv()

# ------------------------------------------------------------------- soldi

# Budget del piano di accumulo. Cambiando questo numero cambia tutto il resto:
# il tetto straordinario e le tranche sono espressi in MESI EQUIVALENTI, non in euro.
BUDGET_MENSILE_EUR = _env_float("BOTBTC_BUDGET_EUR", 200.0)

# Tetto dello sforzo straordinario per ciclo di mercato, in mesi equivalenti di budget
# (F2.5 del piano). None = ancora da decidere dall'utente: e' l'unico parametro che
# dipende da quanto puo' permettersi, non dai dati. Finche' e' None il bot non promette
# tranche: lo dichiara nel messaggio invece di inventare un numero.
TETTO_STRAORDINARIO_MESI = (
    _env_float("BOTBTC_TETTO_MESI", 0.0) or None
)

# Quante volte il versamento normale puo' valere una settimana di stato straordinario.
# Valori provvisori: la taratura vera arriva in F2.4/F2.5, dopo il test storico F2.3.
MOLTIPLICATORE_MIN = _env_float("BOTBTC_MOLT_MIN", 1.5)
MOLTIPLICATORE_MAX = _env_float("BOTBTC_MOLT_MAX", 3.0)

# Lo sforzo straordinario si mette in piu' colpi, mai in uno solo (charter, D15).
COLPI_MINIMI_STRAORDINARIO = _env_int("BOTBTC_COLPI_MIN", 3)

# ------------------------------------------------------- finestre e soglie

# Finestra del percentile MVRV, in giorni. 1460 = 4 anni, la scelta di docs/02 §2.
# Il criterio (g) di F2.3 richiede di rifare il test anche a 2, 3 e 5 anni.
FINESTRA_PERCENTILE_GIORNI = _env_int("BOTBTC_FINESTRA_PCT", 1460)
FINESTRE_PERCENTILE_SENSIBILITA = (730, 1095, 1460, 1825)

# Soglie della regola dei tre stati. NON si toccano a mano: escono dalla calibrazione sulla quota
# di giorni descritta in docs/04 §1.6 e sono state fissate prima del test storico. Cambiandole,
# i numeri di docs/04 non valgono piu'.
SOGLIA_STRAORDINARIO = _env_float("BOTBTC_SOGLIA_STR", 0.4257)   # ricalibrata il 2026-09-22 (D41)
SOGLIA_FRENO = _env_float("BOTBTC_SOGLIA_FRENO", 0.2315)         # ricalibrata il 2026-09-22 (D41)
# Giorni consecutivi di mercato caro prima che il freno possa accendersi (docs/04 §3):
# senza questo, il freno si accende anche a inizio rialzo (dicembre 2020).
DURATA_MINIMA_CARO_GIORNI = _env_int("BOTBTC_DURATA_CARO", 60)
CONFERMA_GIORNI = _env_int("BOTBTC_CONFERMA", 2)

# Parametri degli indicatori (stessi valori usati in docs/02, cambiarli invalida quei numeri).
SMA_LUNGA_GIORNI = 200
DRAWDOWN_FINESTRA_GIORNI = 365
RSI_PERIODO = 14
WMA_SETTIMANE = 200
PI_CYCLE = (111, 350, 2.0)

# Soglie di sanita' dei dati (F1.3).
SALTO_PREZZO_MAX_GIORNALIERO = _env_float("BOTBTC_SALTO_MAX", 0.30)   # 30 % in un giorno
ETA_MASSIMA_PREZZO_GIORNI = 2      # il prezzo di ieri deve esserci
ETA_MASSIMA_MVRV_GIORNI = 3        # MVRV arriva a T+1: tolleranza di un giorno in piu'
ETA_MASSIMA_FNG_GIORNI = 3

# --------------------------------------------------------------- consegna

# Solo storico: l'orario vero lo decide deploy/aphroditebtc-report.timer (09:00 Europe/Rome, gestisce
# da solo il cambio d'ora). Nessun codice usa piu' queste due variabili per decidere quando mandare.
ORA_REPORT_UTC = _env_int("BOTBTC_ORA_REPORT_UTC", 7)
MINUTO_REPORT_UTC = _env_int("BOTBTC_MINUTO_REPORT_UTC", 0)
FUSO_UTENTE = _env("BOTBTC_FUSO", "Europe/Rome")

TELEGRAM_TOKEN = _env("BOTBTC_TELEGRAM_TOKEN")     # segreto: solo da .env / ambiente
TELEGRAM_CHAT_ID = _env("BOTBTC_TELEGRAM_CHAT_ID")

# ------------------------------------------------------------------- dati

# Serie di prezzo usata dal bot live: le chiusure Coinbase, che sono disponibili
# subito (l'MVRV di CoinMetrics arriva il giorno dopo). Vedi D12 e D22:
# le due serie di prezzo non si mescolano mai dentro lo stesso calcolo.
SERIE_PREZZO_LIVE = _env("BOTBTC_SERIE_PREZZO", "coinbase")

TIMEOUT_RETE_SECONDI = _env_int("BOTBTC_TIMEOUT", 20)
TENTATIVI_RETE = _env_int("BOTBTC_TENTATIVI", 3)


def parametri_motore():
    """Costruisce i parametri del motore dalla configurazione (unica fonte di verita')."""
    from botbtc import engine

    return engine.Parametri(soglia_straordinario=SOGLIA_STRAORDINARIO,
                            soglia_freno=SOGLIA_FRENO,
                            durata_minima_caro=DURATA_MINIMA_CARO_GIORNI,
                            conferma_giorni=CONFERMA_GIORNI,
                            molt_min=MOLTIPLICATORE_MIN,
                            molt_max=MOLTIPLICATORE_MAX,
                            colpi_minimi=COLPI_MINIMI_STRAORDINARIO)


def riassunto():
    """Dizionario ordinato dei parametri, per --dry-run e per i log."""
    tetto = "da decidere (F2.5)" if TETTO_STRAORDINARIO_MESI is None else f"{TETTO_STRAORDINARIO_MESI:g} mesi equivalenti"
    return {
        "budget mensile": f"{BUDGET_MENSILE_EUR:g} EUR",
        "tetto straordinario per ciclo": tetto,
        "moltiplicatore straordinario": f"{MOLTIPLICATORE_MIN:g}x - {MOLTIPLICATORE_MAX:g}x, in almeno {COLPI_MINIMI_STRAORDINARIO} colpi",
        "finestra percentile": f"{FINESTRA_PERCENTILE_GIORNI} giorni ({FINESTRA_PERCENTILE_GIORNI/365:.1f} anni)",
        "soglie stati (straordinario / freno)": f"{SOGLIA_STRAORDINARIO:g} / {SOGLIA_FRENO:g}",
        "freno solo dopo": f"{DURATA_MINIMA_CARO_GIORNI} giorni consecutivi di mercato caro",
        "conferma cambio stato": f"{CONFERMA_GIORNI} giorni consecutivi",
        "finestre per il test di sensibilita'": ", ".join(str(f) for f in FINESTRE_PERCENTILE_SENSIBILITA),
        "serie prezzo del bot live": SERIE_PREZZO_LIVE,
        "salto di prezzo sospetto": f"oltre {SALTO_PREZZO_MAX_GIORNALIERO*100:.0f} % in un giorno",
        "eta' massima dei dati (prezzo/MVRV/F&G)": f"{ETA_MASSIMA_PREZZO_GIORNI}/{ETA_MASSIMA_MVRV_GIORNI}/{ETA_MASSIMA_FNG_GIORNI} giorni",
        "orario report": "09:00 ora italiana sul VPS (lo decide deploy/aphroditebtc-report.timer); sul PC: a mano",
        "token Telegram": "configurato" if TELEGRAM_TOKEN else "MANCANTE (.env)",
        "messaggi a sorpresa": (f"{PING_PER_SETTIMANA} a settimana, {PING_ORA_DA}-{PING_ORA_A}, "
                                f"{'lunedì-venerdì' if PING_SOLO_FERIALI else 'tutti i giorni'}"
                                if PING_PER_SETTIMANA > 0 else "spenti"),
        "commento AI": (f"{LLM_MODELLO} via {LLM_URL}" if (LLM_CHIAVE and LLM_URL and LLM_MODELLO)
                        else "non configurato (servono llmapi, BOTBTC_LLM_URL, BOTBTC_LLM_MODELLO)"),
        "chat_id Telegram": TELEGRAM_CHAT_ID or "MANCANTE (.env)",
        "rete": f"timeout {TIMEOUT_RETE_SECONDI}s, {TENTATIVI_RETE} tentativi",
    }


# ------------------------------------------------------------ commento AI (D44)
# /ai_commentary: il report di oggi raccontato da un modello linguistico (bot/commento_ai.py).
# La chiave sta in bot/.env con il nome che le ha dato l'utente, "llmapi" (oppure BOTBTC_LLM_KEY).
# URL e modello dipendono dal fornitore: qualunque API compatibile con OpenAI (.../chat/completions)
# oppure Anthropic (.../v1/messages). Esempi:
#   BOTBTC_LLM_URL=https://api.openai.com/v1/chat/completions        BOTBTC_LLM_MODELLO=gpt-4o-mini
#   BOTBTC_LLM_URL=https://api.anthropic.com/v1/messages             BOTBTC_LLM_MODELLO=claude-...
LLM_CHIAVE = _env("BOTBTC_LLM_KEY") or _env("llmapi")
LLM_URL = _env("BOTBTC_LLM_URL")
LLM_MODELLO = _env("BOTBTC_LLM_MODELLO")
LLM_TIMEOUT_SECONDI = _env_int("BOTBTC_LLM_TIMEOUT", 90)
# Quanti /ai_commentary al giorno per ogni persona autorizzata (ogni commento è una chiamata a pagamento sul tuo
# account). Il proprietario non ha limiti. 0 = nessun limite nemmeno per gli altri.
AI_COMMENTI_AL_GIORNO = _env_int("BOTBTC_AI_AL_GIORNO", 1)


# ------------------------------------------------------ messaggi a sorpresa (D46)
# Il polso (il messaggio breve) N volte a settimana, a un'ora casuale della fascia lavorativa, perché il bot non stia
# zitto per settimane quando il mercato è fermo. BOTBTC_SORPRESE_SETTIMANA=0 li spegne.
PING_PER_SETTIMANA = _env_int("BOTBTC_SORPRESE_SETTIMANA", 3)
try:
    PING_ORA_DA, PING_ORA_A = (int(x) for x in (_env("BOTBTC_SORPRESE_ORE", "10-18") or "10-18").split("-"))
except ValueError:
    PING_ORA_DA, PING_ORA_A = 10, 18
PING_SOLO_FERIALI = (_env("BOTBTC_SORPRESE_FERIALI", "1") or "1") != "0"
