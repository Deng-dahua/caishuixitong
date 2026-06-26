@echo off
echo === Tax System Diagnostic ===
echo.

echo [1] Python path check:
if exist "C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe" (
    echo   OK
) else (
    echo   FAIL - Python not found
    goto :end
)

echo.
echo [2] Python version:
"C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe" --version

echo.
echo [3] Port 8001 check:
netstat -ano | findstr ":8001" | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo   8001 is IN USE
) else (
    echo   8001 is FREE
)

echo.
echo [4] main.py syntax check:
"C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe" -c "import py_compile; py_compile.compile('main.py', doraise=True); print('   main.py syntax OK')"

echo.
echo [5] engine module check:
"C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe" -c "from engine import save_analysis_memory; print('   engine module OK')"

echo.
echo [6] Full import test:
"C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe" -c "import importlib,sys; sys.path.insert(0,'.'); spec=importlib.util.spec_from_file_location('main','main.py'); mod=importlib.util.module_from_spec(spec); print('   main.py imports OK')"

echo.
echo === Diagnostic complete ===
pause
:end
