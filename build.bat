@echo off
echo Building SocialClip Downloader EXE...

REM Check if pyinstaller is installed
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Build the EXE
if exist "assets\icon.ico" (
    pyinstaller --onefile --noconsole --name "SocialClip Downloader" --icon "assets/icon.ico" socialclip_downloader.py
) else (
    pyinstaller --onefile --noconsole --name "SocialClip Downloader" socialclip_downloader.py
)

REM Copy EXE to project root
if exist "dist\SocialClip Downloader.exe" (
    copy "dist\SocialClip Downloader.exe" .
    echo Build complete. EXE is in the project root and dist/ folder.
) else (
    echo Build failed or EXE not found in dist/.
)