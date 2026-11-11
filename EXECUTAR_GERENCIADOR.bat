@echo off
rem ======================================================================
rem EXECUTAR_GERENCIADOR.bat
rem ======================================================================
rem Inicializador rapido para o Gerenciador de Avatares VRChat no GTA V.
rem Permite executar de forma interativa com duplo clique no Windows.
rem ======================================================================

cd /d "%~dp0"
title Gerenciador de Avatares VRChat - GTA V

echo ======================================================================
echo    GERENCIADOR DE AVATARES VRChat PARA GTA V (ORQUESTRADOR MESTRE)
echo ======================================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao foi encontrado no PATH do sistema.
    echo Por favor, instale o Python 3.10+ e adicione-o as variaveis de ambiente.
    echo.
    pause
    exit /b 1
)

python run_mod_manager.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [AVISO] O script encerrou com codigo de erro %ERRORLEVEL%.
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [CONCLUIDO] Operacao finalizada com sucesso.
pause
