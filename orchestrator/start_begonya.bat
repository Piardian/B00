@echo off
chcp 65001 > nul
title Begonya - Macro & SMC Trading System
echo ======================================================================
echo  🌺 BEGONYA: KURUMSAL MAKRO REJİM & SMC CHECKLIST İŞLEM SİSTEMİ 🌺
echo ======================================================================
cd /d "%~dp0.."
python orchestrator\start_begonya.py
pause
