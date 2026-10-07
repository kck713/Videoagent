@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "CLAUDE=claude"
where claude >nul 2>nul && goto launch
if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
if exist "%USERPROFILE%\.local\bin\claude.exe" goto launch

echo Claude Code가 없어 설치합니다. 공식 설치 프로그램 사용, 관리자 권한 불필요
curl -fsSL https://claude.ai/install.cmd -o "%TEMP%\claude_install.cmd"
if errorlevel 1 goto fail
call "%TEMP%\claude_install.cmd"
del "%TEMP%\claude_install.cmd" >nul 2>nul
if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
if not exist "%USERPROFILE%\.local\bin\claude.exe" goto fail

:launch
echo ============================================
echo  Claude Code - 캡컷 자동 편집 에이전트
echo  처음이면 브라우저가 열립니다. Claude Pro 계정으로 로그인하세요.
echo.
echo  사용 예:
echo    /edit 원본 1010_인터뷰 talk_short
echo    /edit 원본 1010_인터뷰 target 60초로, 계기 부분 위주
echo    /verify-draft 1010_인터뷰
echo  끝내려면 /exit
echo ============================================
if not defined ANTHROPIC_API_KEY goto run
echo.
echo [주의] 이 PC에 ANTHROPIC_API_KEY 가 설정되어 있습니다.
echo        Claude Code가 이 키를 쓸지 물으면 No 를 고르세요. Yes면 Pro 구독이 아니라 API 요금이 나갑니다.
echo.
:run
"%CLAUDE%"
exit /b 0

:fail
echo.
echo [오류] Claude Code 설치에 실패했습니다.
echo PowerShell에서 다음을 실행해 보세요:  irm https://claude.ai/install.ps1 ^| iex
echo 또는 Claude 데스크톱 앱 claude.com/download 의 Code 탭에서 이 폴더를 열어도 됩니다.
pause
exit /b 1
