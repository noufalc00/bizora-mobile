@echo off
setlocal
echo.
echo ============================================================
echo BIZORA - Deploy mobile web for phone access (PC can be OFF)
echo ============================================================
echo.
echo Your PC server (start_cloud_mobile.py) stops when PC is off.
echo You need a free cloud host that runs 24/7, e.g. Render.com
echo.
echo STEP 1 - Push this folder to GitHub
echo   git init
echo   git add .
echo   git commit -m "Add cloud mobile web"
echo   Create repo on github.com, then:
echo   git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
echo   git push -u origin main
echo.
echo STEP 2 - Deploy on Render (render.com)
echo   1. Sign up / log in
echo   2. New + ^> Blueprint
echo   3. Connect your GitHub repo
echo   4. Render reads render.yaml automatically
echo.
echo STEP 3 - Set environment variables in Render dashboard
echo   SUPABASE_URL     = same as your .env
echo   SUPABASE_KEY     = same service role key as your .env
echo   MOBILE_COMPANY_ID = 1
echo   (MOBILE_DATA_SOURCE=supabase is already set in render.yaml)
echo.
echo STEP 4 - After deploy finishes
echo   Open the https://bizora-mobile.onrender.com URL on your phone
echo   Bookmark it - works on any network, PC off is OK
echo.
echo NOTE: Free Render sleeps after ~15 min idle; first open may take ~30 sec.
echo ============================================================
echo.
pause
