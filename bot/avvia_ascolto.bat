@echo off
REM AphroditeBTC - resta in ascolto e risponde ai comandi Telegram.
REM Doppio clic per avviare. Per fermare: chiudi questa finestra, oppure Ctrl-C.
REM Nota: finche' il bot non gira sul VPS (fase F5), i comandi funzionano SOLO mentre
REM questa finestra e' aperta e il PC e' acceso. Il report quotidiano, invece, e' un altro
REM comando (--report) e non ha bisogno di questo.
cd /d "%~dp0.."
title AphroditeBTC - in ascolto
python3 bot\main.py --ascolta
echo.
echo L'ascolto si e' fermato. Premi un tasto per chiudere.
pause >nul
