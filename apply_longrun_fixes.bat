@echo off
REM Usage: apply_longrun_fixes.bat [path\to\trading_2_live4.py]   (requires REV-FIX v1 already applied)
setlocal
set "SRC=%~1"
if "%SRC%"=="" set "SRC=trading_2_live4.py"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
echo [1/3] Applying REV-FIX v2 to %SRC% (backup is created automatically)
%PY% "%~dp0apply_longrun_fixes.py" "%SRC%" --inplace
if errorlevel 1 (echo [FAILED] nothing was changed & exit /b 1)
echo [2/3] Running long-run tests
%PY% "%~dp0test_longrun.py" "%SRC%"
if errorlevel 1 (echo [FAILED] tests failed - restore the .bak file & exit /b 1)
echo [3/3] DONE
endlocal
