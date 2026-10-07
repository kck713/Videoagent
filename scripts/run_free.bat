@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
echo ============================================
echo  캡컷 자동 편집 에이전트 - 무료 모드
echo  편집 계획은 claude.ai 무료 대화창에서 받습니다.
echo  API 키도, 유료 구독도 필요 없습니다.
echo  ※ 실행 전에 캡컷을 완전히 종료하세요
echo ============================================
set /p NAME=프로젝트 이름 (예: 1010_인터뷰): 
if "%NAME%"=="" set NAME=auto_%RANDOM%
set /p STYLE_NO=스타일 (1=인터뷰 target, 2=토크 숏폼 talk_short) [1]: 
set STYLE=target
if "%STYLE_NO%"=="2" set STYLE=talk_short
set /p TARGET=목표 길이(초, 비우면 자동): 
set /p BRIEF=편집 요청 한 줄 (비워도 됨): 
set /p MULTI=여러 카메라로 찍었나요? (y/N): 
set W=work\%NAME%
set TGT=
if not "%TARGET%"=="" set TGT=--target %TARGET%
set MC=
if /I "%MULTI%"=="y" set MC=--multicam
set BGMARG=
for %%F in ("BGM\*.mp3" "BGM\*.wav" "BGM\*.m4a") do if exist "%%~F" set BGMARG=--bgm "%%~fF"

echo.
echo [1/4] 영상 분석 - 받아쓰기, 얼굴 위치. 처음엔 모델을 내려받아 오래 걸립니다
python capcut_agent\agent.py analyze --clips 원본 --broll B롤 --work "%W%" %MC%
if errorlevel 1 goto fail
python capcut_agent\agent.py plan --work "%W%" --style %STYLE% --brief "%BRIEF%" %TGT% --prompt-only
if errorlevel 1 goto fail
python capcut_agent\agent.py clip "%W%\plan_prompt.txt"
start "" "https://claude.ai/new"
echo.
echo [2/4] claude.ai 에서 편집 계획 받기
echo   1. 방금 열린 claude.ai 새 대화 입력창에 Ctrl+V 로 붙여넣고 보내세요.
echo      - 프롬프트는 이미 클립보드에 복사되어 있습니다.
echo   2. 답변이 끝나면 답변 아래 '복사' 버튼으로 답변 전체를 복사하세요.
echo   3. 이어서 열리는 메모장에 Ctrl+V 로 붙여넣고, 저장한 뒤 메모장을 닫으세요.
pause

:paste
type nul > "%W%\edit_plan.json"
notepad "%W%\edit_plan.json"
echo.
echo [3/4] 계획 확인
python capcut_agent\agent.py import-plan --work "%W%" --style %STYLE% %TGT%
if errorlevel 1 goto retry
goto build

:retry
python capcut_agent\agent.py clip "%W%\edit_plan_fix.txt"
echo.
echo 고칠 내용을 클립보드에 복사했습니다.
echo 같은 claude.ai 대화에 Ctrl+V 로 보내고, 새 답변을 복사한 뒤 아무 키나 누르세요.
echo 메모장이 다시 열리면 새 답변을 붙여넣고 저장 후 닫으세요.
pause
goto paste

:build
echo.
echo [4/4] 캡컷 프로젝트 만들기
python capcut_agent\agent.py build --work "%W%" --name "%NAME%" --style %STYLE% %BGMARG%
if errorlevel 1 goto fail
echo.
echo 완료. 캡컷을 열어 '%NAME%' 프로젝트를 확인하세요.
if exist "%W%\preview.jpg" start "" "%W%\preview.jpg"
pause
exit /b 0

:fail
echo.
echo [오류] 위 메시지를 확인하세요. 설치 문제는 python capcut_agent\agent.py check 로 점검할 수 있습니다.
pause
exit /b 1
