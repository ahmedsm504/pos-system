POS CASHIER SYSTEM — SETUP INSTRUCTIONS
==========================================

FIRST TIME SETUP:
  1. Run  create_shortcut.bat  (as Administrator if needed)
  2. A shortcut 'POS System' will appear on your Desktop

DAILY USE:
  - Double-click  run_cashier.vbs  OR the Desktop shortcut
  - Browser opens automatically at http://localhost:8000

FILES:
  run_cashier.vbs      — Silent launcher (no black window)
  start.bat            — Actual startup script
  create_shortcut.bat  — Creates Desktop shortcut
  cashier.ico          — System icon

TROUBLESHOOTING:
  If VBS gives 'cannot find script' error:
    - Make sure the folder path has NO Arabic/special characters
    - Move the entire folder to  C:\pos_system\
    - Then run create_shortcut.bat again

RECOMMENDED FOLDER:  C:\pos_system\
