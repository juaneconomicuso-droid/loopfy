@echo off
setlocal
chcp 65001 >nul
title Loopfy - versao de teste
set "RAIZ=%~dp0"
set "LOOPFY_DEV=1"
set "LOOPFY_SERVER=http://localhost:3100"
set "PY=%RAIZ%desktop\.venv\Scripts\python.exe"

:menu
cls
echo ==============================================
echo   LOOPFY - versao de teste
echo ==============================================
echo.
echo   1  Iniciar o servidor (landing, painel e licenca)
echo   2  Abrir a landing e o painel no navegador
echo   3  Ativar licenca (cole a chave)
echo   4  Ver estado da licenca
echo   5  Login na conta do TikTok (navegador controlado)
echo   6  Verificar acesso ao Gerenciador de LIVE
echo   7  Descobrir a chave de transmissao (grava e procura)
echo   0  Sair
echo.
set /p op=Escolha:
if "%op%"=="1" goto servidor
if "%op%"=="2" goto abrir
if "%op%"=="3" goto ativar
if "%op%"=="4" goto estado
if "%op%"=="5" goto login
if "%op%"=="6" goto status
if "%op%"=="7" goto descobrir
if "%op%"=="0" exit /b
goto menu

:servidor
echo Iniciando o servidor em uma nova janela. Aguarde uns 10 segundos.
start "Loopfy servidor" cmd /k "cd /d %RAIZ%app && npm run dev -- -p 3100"
timeout /t 12 >nul
goto menu

:abrir
start "" http://localhost:3100/
start "" http://localhost:3100/painel
goto menu

:ativar
set /p chave=Chave de licenca (LPFY-XXXX-...):
"%PY%" -m loopfy license --key %chave%
pause
goto menu

:estado
cd /d "%RAIZ%desktop"
"%PY%" -m loopfy license
pause
goto menu

:login
cd /d "%RAIZ%desktop"
echo Entre na conta na janela que abrir. Quando terminar, FECHE a janela do navegador.
"%PY%" -m loopfy login
pause
goto menu

:status
cd /d "%RAIZ%desktop"
"%PY%" -m loopfy status
pause
goto menu

:descobrir
cd /d "%RAIZ%desktop"
"%PY%" -m loopfy discover
pause
goto menu
