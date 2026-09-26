"""Fetcher delle tre fonti dati (F1.1 del piano).

Regole del progetto rispettate qui:
- **solo libreria standard** (urllib): questa e' libreria condivisa, non il livello bot/;
- **mai un valore inventato**: se una fonte non risponde, o risponde in un formato che non
  riconosciamo, si alza `FetchError` con dentro fonte, url e motivo. Il chiamante decide
  se usare il fallback o dirlo nel messaggio — ma nessuno qui tira a indovinare;
- **niente scraping**: solo API pubbliche documentate;
- **solo giorni chiusi**: la candela di oggi e' parziale e non entra nella serie, salvo
  richiesta esplicita (`solo_giorni_chiusi=False`).

Le funzioni restituiscono sempre liste ordinate per data crescente, con `datetime.date`.

Nota sulla rete: dal sandbox cloud di Claude e dalla shell Linux del ponte questi host sono
bloccati; le prove reali vanno fatte dal PC dell'utente o dal VPS (vedi CLAUDE.md §10).
"""

import datetime
import json
import time
import urllib.error
import urllib.request

UA = "botbtc/1.0 (bot personale, uso non commerciale)"

COINBASE_URL = "https://api.exchange.coinbase.com/products/{prodotto}/candles"
BINANCE_URL = "https://api.binance.com/api/v3/klines"
FNG_URL = "https://api.alternative.me/fng/"
COINMETRICS_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"


class FetchError(Exception):
    """Una fonte non ha risposto, o ha risposto qualcosa che non sappiamo leggere."""

    def __init__(self, fonte, url, motivo):
        self.fonte = fonte
        self.url = url
        self.motivo = motivo
        super().__init__(f"fonte '{fonte}' non utilizzabile: {motivo} — {url}")


def _oggi_utc():
    return datetime.datetime.now(datetime.timezone.utc).date()


def _http_json(url, fonte, timeout=20, tentativi=3, pausa=1.5):
    """GET che restituisce JSON o alza FetchError. Ritenta solo su errori transitori."""
    ultimo = None
    for n in range(1, tentativi + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    ultimo = f"HTTP {resp.status}"
                else:
                    grezzo = resp.read()
                    try:
                        return json.loads(grezzo.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise FetchError(fonte, url, f"risposta non JSON ({exc})")
        except urllib.error.HTTPError as exc:
            ultimo = f"HTTP {exc.code}"
            if exc.code in (400, 401, 403, 404, 422):   # errori nostri: ritentare non serve
                raise FetchError(fonte, url, ultimo)
        except urllib.error.URLError as exc:
            ultimo = f"rete non raggiungibile ({exc.reason})"
        except TimeoutError:
            ultimo = f"timeout dopo {timeout}s"
        if n < tentativi:
            time.sleep(pausa * n)
    raise FetchError(fonte, url, f"{ultimo} dopo {tentativi} tentativi")


def _filtra_giorni_chiusi(righe, solo_giorni_chiusi):
    if not solo_giorni_chiusi:
        return righe
    oggi = _oggi_utc()
    return [r for r in righe if r[0] < oggi]

# ------------------------------------------------------------------ prezzo

def prezzo_coinbase(da, a, prodotto="BTC-USD", timeout=20, tentativi=3, solo_giorni_chiusi=True):
    """Chiusure giornaliere da Coinbase Exchange (max 300 candele per chiamata, quindi a blocchi).

    Ritorna [(date, close)] crescente. E' la serie usata dal backtest e dal bot live (D12/D22).
    """
    righe = {}
    blocco = datetime.timedelta(days=290)
    inizio = da
    while inizio <= a:
        fine = min(inizio + blocco, a)
        url = (f"{COINBASE_URL.format(prodotto=prodotto)}?granularity=86400"
               f"&start={inizio.isoformat()}T00:00:00Z&end={fine.isoformat()}T00:00:00Z")
        dati = _http_json(url, "coinbase", timeout, tentativi)
        if not isinstance(dati, list):
            raise FetchError("coinbase", url, f"formato inatteso ({type(dati).__name__})")
        for candela in dati:
            # [time, low, high, open, close, volume]
            if not isinstance(candela, list) or len(candela) < 5:
                raise FetchError("coinbase", url, "candela in formato inatteso")
            giorno = datetime.datetime.fromtimestamp(candela[0], datetime.timezone.utc).date()
            if da <= giorno <= a:
                righe[giorno] = float(candela[4])
        inizio = fine + datetime.timedelta(days=1)
    return _filtra_giorni_chiusi(sorted(righe.items()), solo_giorni_chiusi)


def prezzo_binance(da, a, simbolo="BTCUSDT", timeout=20, tentativi=3, solo_giorni_chiusi=True):
    """Fallback di emergenza: chiusure giornaliere Binance.

    ATTENZIONE: BTCUSDT non e' BTC-USD di Coinbase. Va salvato con la sua `fonte` e usato
    per non restare ciechi, non per sostituire silenziosamente la serie principale
    (differenze tipiche sotto l'1 %, ma sono due mercati diversi).
    """
    righe = {}
    inizio_ms = int(datetime.datetime.combine(da, datetime.time(), datetime.timezone.utc).timestamp() * 1000)
    fine_ms = int(datetime.datetime.combine(a, datetime.time(23, 59, 59), datetime.timezone.utc).timestamp() * 1000)
    cursore = inizio_ms
    while cursore <= fine_ms:
        url = (f"{BINANCE_URL}?symbol={simbolo}&interval=1d&limit=1000"
               f"&startTime={cursore}&endTime={fine_ms}")
        dati = _http_json(url, "binance", timeout, tentativi)
        if not isinstance(dati, list):
            raise FetchError("binance", url, f"formato inatteso ({type(dati).__name__})")
        if not dati:
            break
        for k in dati:
            giorno = datetime.datetime.fromtimestamp(k[0] / 1000, datetime.timezone.utc).date()
            if da <= giorno <= a:
                righe[giorno] = float(k[4])
        ultimo_open = dati[-1][0]
        if len(dati) < 1000:
            break
        cursore = ultimo_open + 86_400_000
    return _filtra_giorni_chiusi(sorted(righe.items()), solo_giorni_chiusi)


def prezzo_con_fallback(da, a, timeout=20, tentativi=3, solo_giorni_chiusi=True):
    """Prova Coinbase, poi Binance. Ritorna (righe, fonte_usata, errori_incontrati).

    Non nasconde il problema: se ha usato il fallback, `errori` contiene l'errore della
    primaria, che il bot deve dichiarare nel messaggio.
    """
    errori = []
    for fonte, funzione in (("coinbase", prezzo_coinbase), ("binance", prezzo_binance)):
        try:
            righe = funzione(da, a, timeout=timeout, tentativi=tentativi,
                             solo_giorni_chiusi=solo_giorni_chiusi)
            if righe:
                return righe, fonte, errori
            errori.append(FetchError(fonte, "-", "nessuna candela nel periodo richiesto"))
        except FetchError as exc:
            errori.append(exc)
    raise FetchError("prezzo", "coinbase+binance",
                     "nessuna fonte disponibile: " + " | ".join(str(e) for e in errori))

# ----------------------------------------------------------- fear & greed

def fear_and_greed(limite=0, timeout=20, tentativi=3, solo_giorni_chiusi=False):
    """Indice Fear & Greed di alternative.me. limite=0 = tutta la storia (dal 2018-02-01).

    `solo_giorni_chiusi=False` di default: l'indice del giorno corrente e' gia' definitivo
    quando lo pubblicano (aggiornamento ~00:00 UTC), non e' una candela parziale.
    """
    url = f"{FNG_URL}?limit={limite}&format=json"
    dati = _http_json(url, "alternative.me", timeout, tentativi)
    voci = dati.get("data") if isinstance(dati, dict) else None
    if not isinstance(voci, list) or not voci:
        raise FetchError("alternative.me", url, "campo 'data' assente o vuoto")
    righe = {}
    for v in voci:
        try:
            giorno = datetime.datetime.fromtimestamp(int(v["timestamp"]), datetime.timezone.utc).date()
            righe[giorno] = int(v["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FetchError("alternative.me", url, f"voce illeggibile ({exc})")
    return _filtra_giorni_chiusi(sorted(righe.items()), solo_giorni_chiusi)

# ------------------------------------------------------------------- mvrv

def mvrv_coinmetrics(da, a, timeout=30, tentativi=3):
    """MVRV, market cap e PriceUSD giornalieri da CoinMetrics Community.

    Ritorna [(date, mvrv, market_cap, price_usd)]. Nessuna chiave API.
    Ritardo strutturale: il dato del giorno T compare il giorno T+1 (docs/02 §1),
    quindi qui non c'e' filtro sui giorni chiusi: si prende quello che c'e'.
    """
    url = (f"{COINMETRICS_URL}?assets=btc&metrics=CapMVRVCur,CapMrktCurUSD,PriceUSD"
           f"&frequency=1d&start_time={da.isoformat()}&end_time={a.isoformat()}"
           f"&page_size=10000&pretty=false")
    righe = {}
    pagine = 0
    while url:
        dati = _http_json(url, "coinmetrics", timeout, tentativi)
        voci = dati.get("data") if isinstance(dati, dict) else None
        if voci is None:
            raise FetchError("coinmetrics", url, "campo 'data' assente")
        for v in voci:
            try:
                giorno = datetime.date.fromisoformat(v["time"][:10])
                righe[giorno] = (float(v["CapMVRVCur"]), float(v["CapMrktCurUSD"]), float(v["PriceUSD"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise FetchError("coinmetrics", url, f"voce illeggibile ({exc})")
        url = dati.get("next_page_url")
        pagine += 1
        if pagine > 50:
            raise FetchError("coinmetrics", url or "-", "troppe pagine: impaginazione sospetta")
    return [(g, *valori) for g, valori in sorted(righe.items())]
