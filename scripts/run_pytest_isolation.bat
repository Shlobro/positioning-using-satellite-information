@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul

set "LOG_DIR=%REPO_ROOT%\artifacts\manual-verification"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "TEMP_PY=%LOG_DIR%\import_check.py"
set "TEMP_PY_REL=artifacts\manual-verification\import_check.py"

set "PYTHON_LAUNCHER=py"
set "STEP_TIMEOUT_SECONDS=20"

echo Repo root: %REPO_ROOT%
echo Logs: %LOG_DIR%
echo Timeout per risky verification step: %STEP_TIMEOUT_SECONDS%s
echo.

echo ==== python_version ====
%PYTHON_LAUNCHER% --version > "%LOG_DIR%\python_version.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
type "%LOG_DIR%\python_version.log"
echo Exit code: %EXIT_CODE%
echo.
if not "%EXIT_CODE%"=="0" goto :fail

echo ==== smoke_script ====
%PYTHON_LAUNCHER% scripts\run_smoke.py > "%LOG_DIR%\smoke_script.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
type "%LOG_DIR%\smoke_script.log"
echo Exit code: %EXIT_CODE%
echo.
if not "%EXIT_CODE%"=="0" goto :fail

(
echo import sys
echo from pathlib import Path
echo sys.path.insert^(0, str^(Path^('src'^).resolve^(^)^)^)
echo import satellite_drone_localization
echo print^('import_ok'^)
) > "%TEMP_PY%"

echo ==== import_check ====
%PYTHON_LAUNCHER% %TEMP_PY_REL% > "%LOG_DIR%\import_check.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
type "%LOG_DIR%\import_check.log"
echo Exit code: %EXIT_CODE%
echo.
if not "%EXIT_CODE%"=="0" goto :fail

echo ==== repo_verification ====
where pwsh >nul 2>&1 && set "PS_EXE=pwsh" || set "PS_EXE=powershell"
%PS_EXE% -NoLogo -NoProfile -Command ^
  "$logFile = '%LOG_DIR%\repo_verification.log';" ^
  "$stdoutPath = [System.IO.Path]::GetTempFileName();" ^
  "$stderrPath = [System.IO.Path]::GetTempFileName();" ^
  "$process = Start-Process -FilePath 'py' -ArgumentList @('scripts\verify_repo.py') -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru;" ^
  "try {" ^
  "  if ($process.WaitForExit(%STEP_TIMEOUT_SECONDS% * 1000)) {" ^
  "    $stdout = if (Test-Path $stdoutPath) { Get-Content $stdoutPath -Raw } else { '' };" ^
  "    $stderr = if (Test-Path $stderrPath) { Get-Content $stderrPath -Raw } else { '' };" ^
  "    $combined = $stdout + $stderr;" ^
  "    Set-Content -Path $logFile -Value $combined -NoNewline;" ^
  "    if ($combined.Length -gt 0) { Write-Host $combined -NoNewline }" ^
  "    exit $process.ExitCode;" ^
  "  }" ^
  "  Stop-Process -Id $process.Id -Force;" ^
  "  $stdout = if (Test-Path $stdoutPath) { Get-Content $stdoutPath -Raw } else { '' };" ^
  "  $stderr = if (Test-Path $stderrPath) { Get-Content $stderrPath -Raw } else { '' };" ^
  "  $combined = $stdout + $stderr + 'TIMED OUT' + [Environment]::NewLine;" ^
  "  Set-Content -Path $logFile -Value $combined -NoNewline;" ^
  "  if ($combined.Length -gt 0) { Write-Host $combined -NoNewline }" ^
  "  exit 124;" ^
  "} finally {" ^
  "  Remove-Item -LiteralPath $stdoutPath, $stderrPath -ErrorAction SilentlyContinue;" ^
  "}"
set "EXIT_CODE=%ERRORLEVEL%"
echo Exit code: %EXIT_CODE%
echo.
if not "%EXIT_CODE%"=="0" goto :fail

echo Verification script completed.
echo Inspect logs in "%LOG_DIR%".
echo.
pause
popd >nul
exit /b 0

:fail
echo Verification script stopped after a failed or timed out step.
echo Inspect logs in "%LOG_DIR%".
echo.
pause
popd >nul
exit /b 1
