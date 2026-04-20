@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul

set "LOG_DIR=%REPO_ROOT%\artifacts\manual-verification"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "TEMP_PY=%LOG_DIR%\import_check.py"
set "TEMP_PY_REL=artifacts\manual-verification\import_check.py"

set "PYTHON_EXE=py -3.12"
set "STEP_TIMEOUT_SECONDS=20"

echo Repo root: %REPO_ROOT%
echo Logs: %LOG_DIR%
echo Timeout per risky pytest step: %STEP_TIMEOUT_SECONDS%s
echo.

call :run_simple "python_version" %PYTHON_EXE% --version
if errorlevel 1 goto :fail

call :run_simple "smoke_script" %PYTHON_EXE% scripts\run_smoke.py
if errorlevel 1 goto :fail

(
echo import sys
echo from pathlib import Path
echo sys.path.insert^(0, str^(Path^('src'^).resolve^(^)^)^)
echo import satellite_drone_localization
echo print^('import_ok'^)
) > "%TEMP_PY%"

call :run_simple "import_check" %PYTHON_EXE% %TEMP_PY_REL%
if errorlevel 1 goto :fail

call :run_simple "collect_smoke_tests" cmd /c "set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 && %PYTHON_EXE% -m pytest tests\test_smoke_pipeline.py --collect-only -q"
if errorlevel 1 goto :fail

call :run_simple "collect_cli_test" cmd /c "set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 && %PYTHON_EXE% -m pytest tests\test_cli.py --collect-only -q"
if errorlevel 1 goto :fail

call :run_timed "exec_smoke_yaml" "set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; & py -3.12 -m pytest tests\test_smoke_pipeline.py::test_run_smoke_writes_yaml_snapshot -q -p no:cacheprovider"
if errorlevel 1 goto :fail

call :run_timed "exec_smoke_artifacts" "set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; & py -3.12 -m pytest tests\test_smoke_pipeline.py::test_run_smoke_writes_required_artifacts -q -p no:cacheprovider"
if errorlevel 1 goto :fail

call :run_timed "exec_cli_test" "set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; & py -3.12 -m pytest tests\test_cli.py::test_cli_main_creates_run -q -p no:cacheprovider"
if errorlevel 1 goto :fail

echo.
echo Verification script completed.
echo Inspect logs in "%LOG_DIR%".
popd >nul
exit /b 0

:run_simple
set "STEP_NAME=%~1"
shift
set "LOG_FILE=%LOG_DIR%\%STEP_NAME%.log"
echo ==== %STEP_NAME% ====
call %~1 %~2 %~3 %~4 %~5 %~6 %~7 %~8 %~9 > "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
type "%LOG_FILE%"
echo Exit code: %EXIT_CODE%
echo.
exit /b %EXIT_CODE%

:run_timed
set "STEP_NAME=%~1"
set "PS_COMMAND=%~2"
set "LOG_FILE=%LOG_DIR%\%STEP_NAME%.log"
echo ==== %STEP_NAME% ====
pwsh -NoLogo -NoProfile -Command ^
  "$logFile = '%LOG_FILE%';" ^
  "$command = {%PS_COMMAND%};" ^
  "$job = Start-Job -ScriptBlock $command;" ^
  "if (Wait-Job $job -Timeout %STEP_TIMEOUT_SECONDS%) {" ^
  "  Receive-Job $job *>&1 | Tee-Object -FilePath $logFile;" ^
  "  $failed = $job.State -ne 'Completed';" ^
  "  Remove-Job $job -Force;" ^
  "  if ($failed) { exit 1 } else { exit 0 }" ^
  "} else {" ^
  "  Stop-Job $job;" ^
  "  Receive-Job $job *>&1 | Tee-Object -FilePath $logFile;" ^
  "  Remove-Job $job -Force;" ^
  "  Add-Content -Path $logFile -Value 'TIMED OUT';" ^
  "  Write-Host 'TIMED OUT';" ^
  "  exit 124" ^
  "}"
set "EXIT_CODE=%ERRORLEVEL%"
type "%LOG_FILE%"
echo Exit code: %EXIT_CODE%
echo.
exit /b %EXIT_CODE%

:fail
echo Verification script stopped after a failed or timed out step.
echo Inspect logs in "%LOG_DIR%".
popd >nul
exit /b 1
