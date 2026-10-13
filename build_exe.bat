@echo off
REM ============================================================
REM  Gera o programa Algoritmo.exe (rode UMA vez no Windows)
REM  Requer: Python 3.11+ instalado (https://www.python.org)
REM ============================================================
cd /d "%~dp0"

echo [1/4] Criando ambiente de build...
if not exist .venv-build (
    py -3 -m venv .venv-build || goto erro
)
call .venv-build\Scripts\activate.bat || goto erro

echo [2/4] Instalando dependencias...
python -m pip install --upgrade pip || goto erro
python -m pip install -r requirements.txt pyinstaller || goto erro

echo [3/4] Gerando o executavel (pode levar alguns minutos)...
python -m PyInstaller --noconfirm --clean --name Algoritmo --console ^
  --collect-all selenium ^
  --collect-all notebooklm_tools ^
  --collect-all docx ^
  --collect-submodules keyring.backends ^
  --copy-metadata keyring ^
  --copy-metadata notebooklm-mcp-cli ^
  --exclude-module accounts ^
  main.py || goto erro

echo [4/4] Copiando arquivos de apoio...
if exist modelo_relatorio.pdf  copy /y modelo_relatorio.pdf  dist\Algoritmo\ >nul
if exist modelo_relatorio.docx copy /y modelo_relatorio.docx dist\Algoritmo\ >nul
copy /y accounts.exemplo.py dist\Algoritmo\ >nul
copy /y LEIA-ME.txt dist\Algoritmo\ >nul

echo.
echo PRONTO. A pasta para entregar ao usuario e: dist\Algoritmo
echo  - Coloque nela o accounts.py (usuario/senha do Effecti).
echo  - Confirme que modelo_relatorio.pdf e modelo_relatorio.docx estao nela.
echo  - Para abrir: duplo clique em Algoritmo.exe
pause
exit /b 0

:erro
echo.
echo FALHOU. Veja a mensagem acima.
pause
exit /b 1
