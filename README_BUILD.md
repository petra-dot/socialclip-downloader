# Building SocialClip Downloader

## Prerequisites
- Python 3.8 or higher
- pip (Python package installer)
- PyInstaller (will be installed automatically by build.bat if missing)

## How to Build
1. Open a command prompt in the project directory.
2. Run `build.bat`.
3. The script will install PyInstaller if needed and build the EXE.

## Output
- The EXE file will be created in the `dist/` folder.
- A copy will also be placed in the project root for convenience.
- Filename: `SocialClip Downloader.exe`

## Important Notes
- **cookies.txt**: This file is NOT bundled in the EXE. Users must provide their own cookies.txt file for YouTube authentication if needed.
- **ffmpeg**: The application requires ffmpeg to be installed separately. It is not bundled in the EXE. Users must install ffmpeg on their system (e.g., via Chocolatey or manually).