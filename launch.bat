@echo off
copy /Y "\\wsl$\Ubuntu-22.04\home\tako\workspace\claude-token-panel\widget.ps1" "%TEMP%\ctoken_widget.ps1" >nul 2>&1
powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "%TEMP%\ctoken_widget.ps1"
