@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo  재고 품목 적용 (11 DP / 12 SDP / 13 LN, 방염 3종)
echo  ※ 재고 수량은 보존됩니다. 여러 번 돌려도 안전.
echo ================================================
echo.
python migrate_inventory_v2.py
echo.
echo 완료. 브라우저에서 재고관리 화면을 새로고침(F5) 하세요.
pause
