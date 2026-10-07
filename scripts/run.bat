@echo off
chcp 65001 >nul
setlocal
echo ============================================
echo  캡컷 자동 편집 에이전트
echo  - 원본 폴더: 인터뷰 원본 영상
echo  - B롤 폴더: B롤 영상 (같은 이름 .txt 에 설명)
echo  - BGM 폴더: 배경음악 1곡 (선택)
echo  ※ 실행 전에 캡컷을 완전히 종료하세요
echo ============================================
set /p NAME=프로젝트 이름 (예: 1007_인터뷰): 
if "%NAME%"=="" set NAME=auto_%RANDOM%
set /p TARGET=목표 길이(초, 비우면 자동): 
set /p BRIEF=편집 요청 한 줄 (비워도 됨): 
set EXTRA=
if not "%TARGET%"=="" set EXTRA=--target %TARGET%
for %%F in ("%~dp0..\BGM\*.mp3" "%~dp0..\BGM\*.wav" "%~dp0..\BGM\*.m4a") do if exist "%%~F" set BGM=%%~F
if defined BGM set EXTRA=%EXTRA% --bgm "%BGM%"
python "%~dp0..\capcut_agent\agent.py" run --clips "%~dp0..\원본" --broll "%~dp0..\B롤" --name "%NAME%" --work "%~dp0..\work\%NAME%" --brief "%BRIEF%" %EXTRA%
echo.
echo 끝나면 캡컷을 열어 '%NAME%' 프로젝트를 확인하세요.
pause
