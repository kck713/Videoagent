@echo off
chcp 65001 >nul
echo ============================================
echo  Claude API 키 설정
echo  - console.anthropic.com 에서 발급 (API Keys 메뉴, sk-ant- 로 시작)
echo  - 이 컴퓨터의 사용자 환경변수 ANTHROPIC_API_KEY 에 저장됩니다
echo    (폴더 안에는 저장하지 않으므로 폴더를 넘겨도 키는 따라가지 않습니다)
echo ============================================
set /p KEY=API 키 붙여넣기: 
if "%KEY%"=="" (
  echo 입력이 없어 종료합니다.
  pause
  exit /b 1
)
setx ANTHROPIC_API_KEY "%KEY%" >nul
set "ANTHROPIC_API_KEY=%KEY%"
echo.
echo 저장했습니다. 연결을 확인합니다...
python "%~dp0..\capcut_agent\agent.py" check
echo.
echo ※ 이미 열려 있던 명령 창/Claude Code에는 새 키가 반영되지 않습니다. 새로 여세요.
pause
