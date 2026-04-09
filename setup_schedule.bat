@echo off
chcp 65001 >nul
echo [GeekNews 자동 수집 스케줄 등록]
echo.

set PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe
set SCRIPT=C:\Users\user\myclaude\ainews\collect_hada.py

:: 기존 작업 삭제 (있으면)
schtasks /Delete /TN "GeekNews_00" /F >nul 2>&1
schtasks /Delete /TN "GeekNews_06" /F >nul 2>&1
schtasks /Delete /TN "GeekNews_12" /F >nul 2>&1
schtasks /Delete /TN "GeekNews_18" /F >nul 2>&1

:: 00시 수집
schtasks /Create /TN "GeekNews_00" /TR "\"%PYTHON%\" \"%SCRIPT%\"" /SC DAILY /ST 00:00 /F
echo   00:00 등록 완료

:: 06시 수집
schtasks /Create /TN "GeekNews_06" /TR "\"%PYTHON%\" \"%SCRIPT%\"" /SC DAILY /ST 06:00 /F
echo   06:00 등록 완료

:: 12시 수집
schtasks /Create /TN "GeekNews_12" /TR "\"%PYTHON%\" \"%SCRIPT%\"" /SC DAILY /ST 12:00 /F
echo   12:00 등록 완료

:: 18시 수집
schtasks /Create /TN "GeekNews_18" /TR "\"%PYTHON%\" \"%SCRIPT%\"" /SC DAILY /ST 18:00 /F
echo   18:00 등록 완료

echo.
echo [완료] 하루 4번 자동 수집이 등록되었습니다.
echo   데이터: C:\Users\user\myclaude\ainews\data\hada_news.json
echo   오늘글: C:\Users\user\myclaude\ainews\data\today.md
echo   주간글: C:\Users\user\myclaude\ainews\data\week.md
pause
