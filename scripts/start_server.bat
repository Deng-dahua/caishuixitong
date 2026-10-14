@echo off
rem ============================================================
rem  DEPRECATED launcher (kept so existing shortcuts keep working).
rem  It no longer starts the server itself: it delegates to the SINGLE
rem  authoritative launcher in the repository root, so that port already
rem  running checks / logging / browser opening stay in ONE place.
rem  See: ..\start8001.bat
rem ============================================================
call "%~dp0..\start8001.bat"
