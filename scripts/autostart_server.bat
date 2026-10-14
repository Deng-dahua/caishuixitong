@echo off
rem ============================================================
rem  Auto-start entry for the caishuixitong server (port 8001).
rem  Called by the Windows Startup-folder shortcut at user logon.
rem  It launches the SINGLE authoritative launcher (start8001.bat)
rem  in a MINIMIZED window. Closing that window still stops the
rem  server; it comes back automatically at next logon.
rem  Keep this file CRLF + ASCII-only (see start8001.bat header).
rem ============================================================
start "caishuixitong-server" /min cmd /c "%~dp0..\start8001.bat"
