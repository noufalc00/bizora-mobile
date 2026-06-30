@echo off
setlocal EnableExtensions
echo.
echo ============================================================
echo BIZORA - Render Free Tier Deploy (PC OFF mobile access)
echo ============================================================
echo.
echo STATUS CHECK
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo [X] Not a git repo. Run: git init
  goto :end
)
echo [OK] Git repo exists
git log -1 --oneline
echo.
echo STEP 1 - Create GitHub repo (browser)
echo   1. Open https://github.com/new
echo   2. Repository name: bizora-mobile  (or any name)
echo   3. Keep it empty (no README)
echo   4. Click Create repository
echo.
echo STEP 2 - Push code (replace YOUR_USER and YOUR_REPO)
echo   git branch -M main
echo   git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
echo   git push -u origin main
echo.
echo STEP 3 - Deploy on Render free tier
echo   1. Open https://dashboard.render.com
echo   2. Sign up with GitHub
echo   3. New + ^> Blueprint
echo   4. Connect the GitHub repo you just pushed
echo   5. Render detects render.yaml automatically
echo   6. When asked for secrets, enter:
echo        SUPABASE_URL      = from your .env file
echo        SUPABASE_KEY      = service role key from .env
echo      MOBILE_COMPANY_ID is already set to 1 in render.yaml
echo   7. Click Apply / Deploy
echo.
echo STEP 4 - Use on phone
echo   After deploy (~5-10 min), open:
echo   https://bizora-mobile.onrender.com
echo   (exact name may vary in Render dashboard)
echo   Bookmark it. Works with PC OFF and any network.
echo.
echo FREE TIER NOTES
echo   - First page load after idle may take ~30 seconds (cold start)
echo   - 750 free hours per month (enough for personal use)
echo   - .env is NOT pushed to GitHub; secrets go only in Render dashboard
echo.
echo DESKTOP SYNC (do once while PC is on)
echo   Save sales/purchases in BIZORA desktop app
echo   Data syncs to Supabase and appears on mobile web
echo.
:end
echo ============================================================
pause
