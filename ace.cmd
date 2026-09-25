@echo off
rem ACE launcher. Job: find a usable Python, then hand over to ai_code.py.
rem Usage: ace [args]    e.g.  ace --input "what time is it"  |  ace --install-ui  |  ace --setup
rem ---------------------------------------------------------------------------
rem ASCII-ONLY ON PURPOSE. Do not add non-ASCII text (Chinese, emoji, smart
rem quotes) to this file, not even inside rem comments or echo strings.
rem Why: cmd.exe tracks its position in a batch file by byte offset, and that
rem bookkeeping breaks when the file contains multi-byte characters while the
rem console code page changes (chcp 65001 below does exactly that). The symptom
rem is ugly and confusing: cmd resumes reading mid-line and executes the TAIL of
rem a comment as if it were a command, so the user sees
rem     'xxx' is not recognized as an internal or external command
rem with fragments of our own comments. All localized user-facing text lives in
rem Python (locales/*.json), which handles encoding properly.
rem ---------------------------------------------------------------------------
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
rem Set ACE_DIRECT_CHAT=1 to skip the landing screen and go straight to chat.
cd /d "%~dp0"

rem Interpreter resolution order:
rem   1) ACE_PYTHON environment variable (explicit choice)
rem   2) setup_env.py --print-python: ACE_PYTHON -> project .ace_env -> common
rem      local dev envs -> PATH, probing which one can really import the UI deps
rem   3) fall back to any interpreter that starts (works, minus the overlay menu)
rem   4) the py -3 launcher
set "_ACE_PROBE="
if defined ACE_PYTHON (set "_ACE_PROBE=%ACE_PYTHON%")
if not defined _ACE_PROBE (if exist "C:\aider_env\Scripts\python.exe" set "_ACE_PROBE=C:\aider_env\Scripts\python.exe")
if not defined _ACE_PROBE (if exist ".ace_env\Scripts\python.exe" set "_ACE_PROBE=.ace_env\Scripts\python.exe")
if not defined _ACE_PROBE (where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "_ACE_PROBE=python")
if not defined _ACE_PROBE (where py >nul 2>nul && set "_ACE_PROBE=py -3")

set "_ACE_PY="
if defined ACE_PYTHON (set "_ACE_PY=%ACE_PYTHON%")
if not defined _ACE_PY (if defined _ACE_PROBE if exist "setup_env.py" (
    for /f "usebackq delims=" %%p in (`%_ACE_PROBE% "setup_env.py" --print-python 2^>nul`) do set "_ACE_PY=%%p"
))
if not defined _ACE_PY (if defined _ACE_PROBE set "_ACE_PY=%_ACE_PROBE%")

if not defined _ACE_PY (
    echo [ACE] No usable Python found. Install 3.10+ and put it on PATH,
    echo       or set ACE_PYTHON to the full path of your python.exe.
    pause
    exit /b 1
)

rem --setup / --install-ui: prepare UI deps first, then start.
if /i "%~1"=="--setup" (
    "%_ACE_PY%" setup_env.py --ensure || goto :env_failed
    shift
)
if /i "%~1"=="--install-ui" (
    "%_ACE_PY%" setup_env.py --ensure || goto :env_failed
    shift
)

rem ---------------------------------------------------------------------------
rem Frontend dispatch.
rem The TypeScript/Ink frontend is the MAIN UI once both pieces are present:
rem Node on PATH, and frontend\node_modules installed. Anything missing falls
rem back to the Python REPL below -- and says WHICH piece was missing. A silent
rem fallback is how you end up wondering why the new UI never shows up.
rem Force the Python path with:  set ACE_LEGACY_UI=1
rem ---------------------------------------------------------------------------
if defined ACE_LEGACY_UI goto :ace_python
where node >nul 2>nul
if errorlevel 1 (
    echo [ACE] Node was not found on PATH -- the Ink frontend needs Node 18+.
    echo       Falling back to the Python REPL.
    goto :ace_python
)
if not exist "frontend\node_modules\tsx\dist\cli.mjs" (
    echo [ACE] Ink frontend dependencies are not installed yet.
    echo       Install them once with:
    echo           cd frontend
    echo           npm install
    echo       Falling back to the Python REPL for now.
    goto :ace_python
)
rem tsx discovers tsconfig.json from the CURRENT DIRECTORY, not from the
rem location of the file it is given. Run it from the repo root and it finds
rem no tsconfig, falls back to the classic JSX transform, and the first
rem render() dies with "React is not defined" -- while "npm start" keeps
rem working, because there the cwd is frontend. So run it from frontend too.
pushd "%~dp0frontend"
node "node_modules\tsx\dist\cli.mjs" "src\index.tsx" %*
popd
goto :eof

:ace_python
"%_ACE_PY%" ai_code.py --tools --max-history 12 %*
goto :eof

:env_failed
echo [ACE] Environment setup failed ^(reason above^). Offline install: drop the
echo       wheels into vendor\ and retry.
pause
exit /b 1
