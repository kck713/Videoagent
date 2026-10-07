@echo off
chcp 65001 >nul
echo [1/2] ffmpeg 설치 (이미 있으면 건너뜀)
where ffmpeg >nul 2>nul || winget install -e --id Gyan.FFmpeg
echo [2/2] 파이썬 패키지 설치
python -m pip install -r "%~dp0..\capcut_agent\requirements.txt"
echo.
echo 설치 완료. ffmpeg를 새로 설치했다면 이 창을 닫고 다시 여세요.
pause
