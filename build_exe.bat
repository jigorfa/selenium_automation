@echo off
REM ============================================================
REM  Gera o programa Algoritmo.exe (rode UMA vez no Windows)
REM  Requer: Python 3.11+ instalado (https://www.python.org)
REM ============================================================
cd /d "%~dp0"

echo [1/4] Criando ambiente de build...
REM Usa um Python com pacotes prontos (wheels) para todas as dependencias.
REM Versoes muito novas obrigam o pip a compilar (ex.: pyyaml) e pedem o Visual C++.
set PYVER=
for %%V in (3.13 3.12 3.14) do (
    if not defined PYVER (
        py -%%V --version >nul 2>&1 && set PYVER=%%V
    )
)
if not defined PYVER (
    echo Nao achei o Python 3.12, 3.13 ou 3.14. Instale o Python 3.13 em https://www.python.org
    goto erro
)
echo Usando Python %PYVER%

REM Se o ambiente de build foi criado com outra versao, recria
if exist .venv-build (
    .venv-build\Scripts\python.exe -c "import sys; sys.exit(0 if '%%d.%%d' %% sys.version_info[:2] == '%PYVER%' else 1)" >nul 2>&1 || rmdir /s /q .venv-build
)
if not exist .venv-build (
    py -%PYVER% -m venv .venv-build || goto erro
)
call .venv-build\Scripts\activate.bat || goto erro

echo [2/4] Instalando dependencias...
python -m pip install --upgrade pip || goto erro
python -m pip install --prefer-binary -r requirements.txt pyinstaller || goto erro

echo [3/4] Gerando o executavel (pode levar alguns minutos)...
python -m PyInstaller --noconfirm --clean --name Algoritmo --console ^
  --collect-all selenium ^
  --collect-all notebooklm_tools ^
  --collect-all docx ^
  --collect-all anthropic ^
  --collect-submodules pypdf ^
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
