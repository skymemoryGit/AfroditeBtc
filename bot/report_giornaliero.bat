@echo off
REM AphroditeBTC - il giro quotidiano: aggiorna i dati, decide, manda il messaggio, registra.
REM Da lanciare una volta al giorno (a mano, o con l'Utilita' di pianificazione di Windows).
cd /d "%~dp0.."
python3 bot\main.py --report
