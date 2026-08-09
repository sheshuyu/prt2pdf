@echo off
chcp 65001 >nul
echo ================================================
echo   prt2pdf - PyInstaller build (onedir)
echo ================================================
echo.

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

REM onedir: startup ~0.33s vs onefile ~2.1s (no archive extraction)
REM exclude: pywebview pulls in Qt backends it never uses on Windows
pyinstaller --onedir --noconsole --name prt2pdf --icon=icon.ico --add-data "web;web" --add-data "icon.ico;." --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 --exclude-module tkinter --exclude-module customtkinter --exclude-module cefpython3 prt2pdf_webview.py

echo.
if exist "dist\prt2pdf\prt2pdf.exe" (
    echo ================================================
    echo   Done: dist\prt2pdf\prt2pdf.exe
    echo   Ship the whole dist\prt2pdf folder.
    echo ================================================
) else (
    echo ================================================
    echo   FAILED: dist\prt2pdf\prt2pdf.exe not found
    echo   Antivirus may have quarantined it.
    echo   Add this folder to AV exclusions and retry.
    echo ================================================
)
pause
