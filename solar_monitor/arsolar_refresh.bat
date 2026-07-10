@echo off
:: ARSolar - Refresh via Custom Protocol Handler
:: Called by Windows when browser navigates to arsolar://refresh
cd /d "g:\Meu Drive\MP\ProjetoMaker\ARSolar\solar_monitor"

echo [%date% %time%] Iniciando varredura via protocolo... >> arsolar_refresh.log
pythonw monitor.py --force --url "%~1" >> arsolar_refresh.log 2>&1
echo [%date% %time%] Processo de varredura disparado em background. >> arsolar_refresh.log
