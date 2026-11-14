@echo off
chcp 65001 >nul
setlocal
rem ======================================================================
rem RUN_MANAGER.bat / EXECUTAR_GERENCIADOR.bat
rem ======================================================================
rem Quick interactive launcher for the VRChat Avatar to GTA V Manager.
rem Detects VRC2GTAV_LANG or Windows UI locale (en / ja / pt).
rem ======================================================================

cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "RAW_LANG="
if defined VRC2GTAV_LANG (
    set "RAW_LANG=%VRC2GTAV_LANG%"
) else (
    for /f "tokens=3" %%A in ('reg query "HKCU\Control Panel\International" /v LocaleName 2^>nul ^| find /i "LocaleName"') do set "RAW_LANG=%%A"
)

if not defined RAW_LANG goto :lang_en
echo(%RAW_LANG%| findstr /i /r "^pt" >nul && goto :lang_pt
echo(%RAW_LANG%| findstr /i /r "^ja" >nul && goto :lang_ja
goto :lang_en

:lang_pt
set "WIN_TITLE=Gerenciador de Avatares VRChat - GTA V"
set "BANNER_TEXT=   GERENCIADOR DE AVATARES VRChat PARA GTA V (ORQUESTRADOR MESTRE)"
set "ERR_NO_PY=[ERRO] Python não foi encontrado no PATH do sistema."
set "ERR_PY_HINT=Por favor, instale o Python 3.10+ e adicione-o às variáveis de ambiente."
set "WARN_EXIT=[AVISO] O script encerrou com código de erro"
set "DONE_TEXT=[CONCLUÍDO] Operação finalizada com sucesso."
goto :run_launcher

:lang_ja
set "WIN_TITLE=VRChat アバター管理ツール - GTA V"
set "BANNER_TEXT=   VRChat アバター -> GTA V マスターマネージャー"
set "ERR_NO_PY=[エラー] システム PATH に Python が見つかりませんでした。"
set "ERR_PY_HINT=Python 3.10+ をインストールし、環境変数 PATH に追加してください。"
set "WARN_EXIT=[警告] スクリプトは次の終了コードで終了しました:"
set "DONE_TEXT=[完了] 処理が正常に完了しました。"
goto :run_launcher

:lang_en
set "WIN_TITLE=VRChat Avatar Manager - GTA V"
set "BANNER_TEXT=   VRChat AVATAR TO GTA V MANAGER (MASTER ORCHESTRATOR)"
set "ERR_NO_PY=[ERROR] Python was not found in the system PATH."
set "ERR_PY_HINT=Please install Python 3.10+ and add it to your environment variables."
set "WARN_EXIT=[WARN] The script exited with error code"
set "DONE_TEXT=[DONE] Operation completed successfully."

:run_launcher
title %WIN_TITLE%

echo ======================================================================
echo %BANNER_TEXT%
echo ======================================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo %ERR_NO_PY%
    echo %ERR_PY_HINT%
    echo.
    pause
    exit /b 1
)

python run_mod_manager.py %*
set "EXIT_CODE=%ERRORLEVEL%"
if %EXIT_CODE% NEQ 0 (
    echo.
    echo %WARN_EXIT% %EXIT_CODE%.
    echo.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo %DONE_TEXT%
pause
