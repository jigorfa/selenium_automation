@echo off
REM ============================================================
REM  Gera o programa Algoritmo.exe (rode UMA vez no Windows)
REM  Requer: Python 3.11+ instalado (https://www.python.org)
REM  Instala o Claude Code automaticamente se ainda nao estiver instalado.
REM ============================================================
cd /d "%~dp0"

echo [1/5] Verificando o Claude Code...
where claude >nul 2>&1 && goto claude_ok
REM O instalador nativo coloca o claude.exe em %USERPROFILE%\.local\bin
if exist "%USERPROFILE%\.local\bin\claude.exe" goto claude_path

echo Claude Code nao encontrado. Instalando (instalador oficial)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
if errorlevel 1 goto claude_falhou
if not exist "%USERPROFILE%\.local\bin\claude.exe" goto claude_falhou

:claude_path
REM Garante o claude no PATH desta janela (o instalador ja ajusta o PATH do usuario)
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:claude_ok
claude --version
REM No Windows nativo o Claude Code usa o Git Bash; so avisa se faltar
where git >nul 2>&1 || echo AVISO: Git for Windows nao encontrado. O Claude Code precisa dele: https://git-scm.com/downloads/win
goto claude_fim

:claude_falhou
echo.
echo AVISO: nao foi possivel instalar o Claude Code automaticamente.
echo Instale manualmente depois: abra o PowerShell e rode
echo     irm https://claude.ai/install.ps1 ^| iex
echo O build do executavel continua normalmente.
echo.

:claude_fim

echo [2/5] Criando ambiente de build...
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

echo [3/5] Instalando dependencias...
python -m pip install --upgrade pip || goto erro
python -m pip install --prefer-binary -r requirements.txt pyinstaller || goto erro

echo [4/5] Gerando o executavel (pode levar alguns minutos)...
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

echo [5/5] Copiando arquivos de apoio...
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
