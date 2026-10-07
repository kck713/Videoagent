@echo off
chcp 65001 >nul
if exist "%~dp0..\claude_commands" (
  echo [0/2] Claude Code 명령 /edit, /verify-draft 설치
  xcopy /E /I /Y /Q "%~dp0..\claude_commands" "%~dp0..\.claude\commands" >nul
)
echo [1/2] ffmpeg 설치 (이미 있으면 건너뜀)
where ffmpeg >nul 2>nul || winget install -e --id Gyan.FFmpeg
echo [2/2] 파이썬 패키지 설치
python -m pip install -r "%~dp0..\capcut_agent\requirements.txt"
if errorlevel 1 echo [오류] Python이 설치되어 있고 PATH에 등록됐는지 확인하세요.
echo.
echo 설치 완료. ffmpeg를 새로 설치했다면 이 창을 닫고 다시 여세요.
echo Claude API로 자동 편집하려면 API키_설정.bat 을 실행하세요.
pause
