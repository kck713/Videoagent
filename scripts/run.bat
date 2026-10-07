@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
echo ============================================
echo  캡컷 자동 편집 에이전트
echo  - 원본 폴더: 인터뷰 원본 영상
echo  - B롤 폴더: B롤 영상/이미지 (같은 이름 .txt 에 설명)
echo  - BGM 폴더: 배경음악 1곡 (선택)
echo  ※ 실행 전에 캡컷을 완전히 종료하세요
echo  ※ API 키가 없으면 편집 계획은 Claude Code의 /edit 로 하세요
echo ============================================
set /p NAME=프로젝트 이름 (예: 1010_인터뷰): 
if "%NAME%"=="" set NAME=auto_%RANDOM%
set /p STYLE_NO=스타일 (1=인터뷰 target, 2=토크 숏폼 talk_short) [1]: 
set STYLE=target
if "%STYLE_NO%"=="2" set STYLE=talk_short
set /p TARGET=목표 길이(초, 비우면 자동): 
set /p BRIEF=편집 요청 한 줄 (비워도 됨): 
set /p MULTI=여러 카메라로 찍었나요? (y/N): 
set EXTRA=
if not "%TARGET%"=="" set EXTRA=--target %TARGET%
if /I "%MULTI%"=="y" set EXTRA=%EXTRA% --multicam
for %%F in ("BGM\*.mp3" "BGM\*.wav" "BGM\*.m4a") do if exist "%%~F" set BGM=%%~fF
if defined BGM set EXTRA=%EXTRA% --bgm "%BGM%"
python capcut_agent\agent.py run --clips 원본 --broll B롤 --name "%NAME%" --work "work\%NAME%" --style %STYLE% --brief "%BRIEF%" %EXTRA%
echo.
echo 끝나면 캡컷을 열어 '%NAME%' 프로젝트를 확인하세요.
pause
