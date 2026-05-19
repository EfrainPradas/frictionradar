@echo off
ssh -i C:\Ubuntu\home\efraiprada\connections\OwnerIQ.pem -o StrictHostKeyChecking=no admin@3.145.4.238 "cd carreertips/backend && git pull origin main && pm2 restart carreertips-backend" > C:\Users\ADM\deploy_output.txt 2>&1
type C:\Users\ADM\deploy_output.txt
