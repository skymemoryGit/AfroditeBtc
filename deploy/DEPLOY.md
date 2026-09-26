# Mettere AphroditeBTC sul VPS — guida passo passo (F5)

Obiettivo: il report arriva **ogni mattina alle 9:00 senza accendere il PC**, i comandi (`/analisi`,
`/stato`, …) rispondono sempre, e il registro giornaliero si riempie da solo.

Un comando alla volta. Per ognuno: **cosa fa** e **cosa devi vedere**. Se vedi altro, fermati lì.
Tempo: circa un'ora la prima volta.

Cose già a posto, che non servono:
- **niente da installare**: il bot usa solo la libreria standard di Python, e Ubuntu 24 ha già Python 3.12;
- **nessuna porta da aprire**: è il bot che va a chiedere a Telegram, non riceve connessioni. Il firewall resta com'è.

Nella guida `IP_DEL_VPS` è l'indirizzo del tuo VPS Contabo.

---

## 1. Sul PC — pubblicare il codice su GitHub (privato)

**1.1** Su github.com crea un repository **privato**, nome `AphroditeBTC`, **vuoto** (senza README, senza
.gitignore, senza licenza: il progetto li ha già).

**1.2** Nel terminale del PC, entra nella cartella del progetto:
```
cd C:\Users\Ye\Desktop\TapVision\SAAS\Bot_telegram__NoraAIBot\Bot_btc
```

**1.3** Controlla che il repository locale ci sia:
```
git log --oneline
```
Devi vedere almeno i commit della sessione 14. Se git dice *"detected dubious ownership"* (il repository è
stato creato dalla macchina di Claude), lancia una volta il comando che git stesso ti suggerisce
(`git config --global --add safe.directory …`) e riprova.

**1.4** Collega il repository di GitHub:
```
git remote add origin https://github.com/skymemoryGit/AphroditeBTC.git
```

**1.5** Carica:
```
git push -u origin main
```
Si apre il browser per il login a GitHub, la prima volta.
**Cosa devi vedere su GitHub**: le cartelle `bot`, `botbtc`, `data`, `docs`, `deploy`… e **NON** devi vedere
`bot/.env`, `data/botbtc.sqlite3`, `docs/spunti`. Se ne vedi uno, fermati: vuol dire che un segreto è uscito.

---

## 2. Sul VPS — dare al server il permesso di leggere il repository

Il repository è privato: il VPS ha bisogno di una sua chiave, **di sola lettura** e valida solo per questo
repository (una "deploy key"). Così, se un giorno il server venisse compromesso, non potrebbe toccare
nient'altro del tuo account GitHub.

**2.1** Entra nel VPS (come fai sempre, con il tuo utente `skymemory`).

**2.2** Controlla che git ci sia:
```
git --version
```
Se manca: `sudo apt install git`.

**2.3** Crea la chiave del server:
```
ssh-keygen -t ed25519 -C "vps-aphroditebtc" -f ~/.ssh/aphroditebtc_deploy -N ""
```
Crea due file: `aphroditebtc_deploy` (privato, non esce mai dal server) e `aphroditebtc_deploy.pub` (pubblico).

**2.4** Mostra la parte pubblica e copiala:
```
cat ~/.ssh/aphroditebtc_deploy.pub
```

**2.5** Su GitHub: repository `AphroditeBTC` → **Settings → Deploy keys → Add deploy key**. Titolo
`VPS Contabo`, incolla la chiave, **lascia spenta** "Allow write access". Salva.

**2.6** Di' a SSH di usare quella chiave per GitHub. Apri il file di configurazione:
```
nano ~/.ssh/config
```
e aggiungi in fondo:
```
Host github-aphroditebtc
    HostName github.com
    User git
    IdentityFile ~/.ssh/aphroditebtc_deploy
    IdentitiesOnly yes
```
Salva (Ctrl+O, Invio) ed esci (Ctrl+X).

**2.7** Prova:
```
ssh -T github-aphroditebtc
```
La prima volta chiede se ti fidi di github.com: rispondi `yes`. **Devi vedere**: *"Hi skymemoryGit/AphroditeBTC!
You've successfully authenticated, but GitHub does not provide shell access."* È il messaggio giusto.

**2.8** Scarica il codice:
```
git clone github-aphroditebtc:skymemoryGit/AphroditeBTC.git ~/AphroditeBTC
```

---

## 3. Dal PC al VPS — i due file che non passano mai da GitHub

Il token Telegram (`bot/.env`) e la memoria del bot (`data/botbtc.sqlite3`: registro, utenti autorizzati,
impostazioni) viaggiano direttamente dal PC al VPS, mai dal repository.

**3.1** Nel terminale del **PC** (PowerShell):
```
scp C:\Users\Ye\Desktop\TapVision\SAAS\Bot_telegram__NoraAIBot\Bot_btc\bot\.env skymemory@IP_DEL_VPS:~/AphroditeBTC/bot/.env
```

**3.2** Sempre dal **PC**:
```
scp C:\Users\Ye\Desktop\TapVision\SAAS\Bot_telegram__NoraAIBot\Bot_btc\data\botbtc.sqlite3 skymemory@IP_DEL_VPS:~/AphroditeBTC/data/botbtc.sqlite3
```
(Se salti questo passo il bot funziona lo stesso: ricostruisce i dati dai CSV. Perdi però la riga di
registro del 21/09 e l'elenco degli utenti autorizzati.)

**3.3** Sul **VPS**, rendi il token leggibile solo da te:
```
chmod 600 ~/AphroditeBTC/bot/.env
```

---

## 4. Sul VPS — prove a mano, prima di automatizzare

**4.1** Entra nella cartella:
```
cd ~/AphroditeBTC
```

**4.2** Configurazione:
```
python3 bot/main.py --dry-run
```
**Devi vedere**: `token Telegram  configurato` e l'orario `09:00 ora italiana sul VPS`.

**4.3** Le tre fonti di dati, dal VPS (solo lettura, non scrive niente):
```
python3 tests/prova_rete.py
```
**Devi vedere** Coinbase, alternative.me e CoinMetrics rispondere. (Dalla macchina di Claude CoinMetrics era
bloccato: dal VPS deve funzionare. Se non funziona, fermati qui.)

**4.4** Aggiorna i dati e guarda la fotografia di oggi (non manda niente su Telegram):
```
python3 bot/main.py --giornaliero
```
Scarica da solo i giorni mancanti dal 22/09 in poi.

**4.5** Il primo report vero dal VPS:
```
python3 bot/main.py --report
```
**Devi vedere** il messaggio arrivare sul telefono. E poi:
```
python3 bot/main.py --registro
```
**Devi vedere** una riga nuova con la data di oggi.

---

## 5. Sul VPS — i servizi automatici

**5.1** Copia i file dei servizi dove systemd li cerca:
```
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
```

**5.2** Fai rileggere a systemd i file nuovi:
```
sudo systemctl daemon-reload
```

**5.3 — PRIMA DEL PASSO 5.4: sul PC chiudi la finestra di `avvia_ascolto.bat`**, se è aperta.
Telegram accetta un solo ascoltatore per bot: con due accesi vanno in errore tutti e due (*409 Conflict*).

**5.4** L'ascolto dei comandi, sempre acceso:
```
sudo systemctl enable --now aphroditebtc-ascolto.service
```
`enable` = parte da solo a ogni riavvio del server · `--now` = parte anche adesso.

**5.5** Il report delle 9:00:
```
sudo systemctl enable --now aphroditebtc-report.timer
```

**5.6** Il backup delle 3:30:
```
sudo systemctl enable --now aphroditebtc-backup.timer
```

### Controlli

**5.7** L'ascolto gira:
```
systemctl status aphroditebtc-ascolto
```
**Devi vedere** `active (running)` in verde. Esci con `q`.

**5.8** I timer sono programmati:
```
systemctl list-timers | grep aphroditebtc
```
**Devi vedere** due righe: il report (prossima esecuzione domani alle 9:00 ora italiana, cioè 07:00 UTC oggi,
08:00 UTC dopo il 25 ottobre) e il backup.

**5.9** Su Telegram scrivi `/stato`. **Deve rispondere**, e adesso risponde il VPS.

**5.10** Prova il backup subito, senza aspettare la notte:
```
sudo systemctl start aphroditebtc-backup.service
ls ~/backup-aphroditebtc
```
**Devi vedere** un file `botbtc-AAAA-MM-GG.sqlite3`.

**5.11 — Il giorno dopo**: alle 9:00 il report arriva senza che tu faccia niente. È il vero collaudo.

---

## 6. Da adesso in poi

**Sul PC non usare più** `avvia_ascolto.bat` né `report_giornaliero.bat`: con il VPS acceso daresti un 409
Conflict (l'ascolto) o un report doppio (il report). Restano solo come riserva se il VPS fosse giù; in quel
caso prima si ferma il servizio sul VPS (`sudo systemctl stop aphroditebtc-ascolto`).

**Quando il codice cambia** (sul PC, o da un agente):
1. sul PC: `git add …`, `git commit …`, `git push`;
2. sul VPS: `cd ~/AphroditeBTC && git pull`;
3. sul VPS: `sudo systemctl restart aphroditebtc-ascolto`.

Il report non va riavviato: parte da zero ogni mattina e legge il codice nuovo da solo. L'ascolto invece carica
il codice una volta sola, all'avvio: senza il passo 3 continua a rispondere con la versione vecchia.

**Se cambi un file in `deploy/`**: rifai 5.1 e 5.2, poi riavvia il servizio o il timer che hai cambiato.

---

## 7. Se qualcosa non va

| cosa vedi | perché | cosa fare |
|---|---|---|
| nei log dell'ascolto: `409 Conflict` | due ascoltatori sullo stesso bot | chiudi `avvia_ascolto.bat` sul PC |
| alle 9:00 non arriva niente | timer non attivo, o errore nel giro | `systemctl list-timers \| grep aphroditebtc` e `journalctl -u aphroditebtc-report -n 50` |
| il report dice spesso "MVRV non disponibile" | CoinMetrics pubblica il dato di ieri più tardi del solito | sposta il timer alle 10:00 in `deploy/aphroditebtc-report.timer`, poi rifai 5.1, 5.2 e `sudo systemctl restart aphroditebtc-report.timer` |
| `/stato` non risponde | ascolto fermo | `systemctl status aphroditebtc-ascolto` e `journalctl -u aphroditebtc-ascolto -n 50` |
| "token MANCANTE" | `bot/.env` non copiato o nel posto sbagliato | rifai 3.1 e 3.3 |
| una modifica ha rotto il bot | — | `git log --oneline`, poi `git checkout <commit buono>` e `sudo systemctl restart aphroditebtc-ascolto` |

Log in diretta: `journalctl -u aphroditebtc-ascolto -f` (esci con Ctrl+C).
