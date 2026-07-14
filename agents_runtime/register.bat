@echo off
set TOKEN=
for /f "delims=" %%i in ('gcloud auth print-identity-token') do set TOKEN=%%i
set PORTAL=https://coherence-portal-test-894828119087.us-central1.run.app
set AR=https://agents-runtime-test-c5nbfc5meq-uc.a.run.app

echo === 1. Register module (body) ===
curl -s -w "HTTP %%{http_code}\n" -X POST -H "Authorization: Bearer %TOKEN%" -H "Content-Type: application/json" -d "{\"name\":\"Agentes Omnichannel\",\"url\":\"%AR%\",\"description\":\"Runtime multi-agente (Jennifer + 4 Managers + Specialists)\",\"icon\":\"Bot\"}" "%PORTAL%/api/admin/modules/omnichannel-agentes"

echo.
echo === 2. Grant permission (query params) ===
curl -s -w "HTTP %%{http_code}\n" -X POST -H "Authorization: Bearer %TOKEN%" "%PORTAL%/api/admin/permissions?admin_email=viniciusbritor@gmail.com&target_email=viniciusbritor@gmail.com&module_id=omnichannel-agentes&role=super-admin"

echo.
echo === 3. List modules ===
curl -s "%PORTAL%/api/modules"