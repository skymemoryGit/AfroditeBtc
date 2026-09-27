# DEPLOY.md — messa in esercizio su VPS (F5)

Note essenziali. Per il contesto di progetto vedi `CLAUDE.md` e `docs/STATO.md`.

## VPS
- Contabo, Ubuntu 24, utente `skymemory`, hardening SSH/UFW/fail2ban già fatto.
- Path del progetto: `/home/skymemory/telegram_Bot/AfroditeBtc` (stessa cartella di tutti gli altri bot Telegram, NON `~/AphroditeBTC` come si potrebbe pensare leggendo solo i .service).

## Stato (2026-09-27) — F5 completata, bot in esercizio
- Repo clonato su VPS via `git clone` in `~/telegram_Bot/AfroditeBtc`.
- `.env` creato a mano direttamente su VPS (non via scp) con token+chat id reali.
- Database: `python3 bot/main.py --bootstrap` dai CSV già in `data/` — si è scelto di ripartire pulito, **niente registro storico pre-deploy** (quello vecchio, con le righe del periodo di test da PC, è rimasto solo in locale, non è stato portato).
- Collegamento Telegram testato e funzionante (`--telegram-prova`, poi `--report` end-to-end).
- Unit systemd installate in `/etc/systemd/system/` e attive: `aphroditebtc-ascolto.service` (sempre acceso), `aphroditebtc-report.timer` (9:00 Europe/Rome), `aphroditebtc-backup.timer` (3:30 Europe/Rome).

## Bug trovato e corretto in questa sessione
I 3 file `.service` avevano `WorkingDirectory=/home/skymemory/AphroditeBTC` — path sbagliato, causava `chdir` fallito (systemd status 200/CHDIR) al primo avvio del servizio. Corretto in `/home/skymemory/telegram_Bot/AfroditeBtc`, sia nei file installati su VPS sia in questa cartella del repo.
**Non ancora committato su git** — chi lavora qui la prossima volta deve fare `git add deploy/*.service && git commit && git push`, poi sul VPS `git pull` (non sovrascriverà il fix perché è già uguale).

## Prossimi passi
- Committare/pushare la correzione dei `.service` (sopra)
- Verificare che il report delle 9:00 arrivi da solo domani, senza intervento
