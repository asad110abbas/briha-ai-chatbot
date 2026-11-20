# Briha AI Chatbot: deploying on a Linux VM

Target: Ubuntu Server 24.04 LTS, 4 vCPU / 8 GB RAM / 60 GB SSD, Docker Engine + Compose plugin.

## 1. Network checklist (ask IT)
- [ ] Inbound 443 (and 80) to the VM from the office LAN / VPN
- [ ] Outbound from the VM to the data API `host:PORT`
- [ ] Outbound HTTPS to `api.openai.com` (or a proxy, set `HTTPS_PROXY` in `.env`)

## Go-live checklist: `.env` on the VM
These differ from the local test setup. Set them on the server only, after the HTTPS certificate is in place.
- [ ] `APP_ENV=production`: hides the API docs page and rejects changes that don't come from BRIHA's own page
- [ ] `COOKIE_SECURE=true`: the login cookie is only sent over HTTPS (breaks login on plain HTTP, so server only)
- [ ] `APP_BASE_URL=https://<briha address>`: the real address people open
- [ ] `LLM_MODE=openai` and `OPENAI_API_KEY` filled in
- [ ] `DATASOURCE_MODE=rest` and `data_apis.yaml` filled in with the real company APIs
- [ ] Strong, new `POSTGRES_PASSWORD` and `ADMIN_PASSWORD` (not the ones used for testing)
- [ ] `ADMIN_RESET_PASSWORD` off (false or not set)
- [ ] `chmod 600 .env` so only the owner can read it
- [ ] After start: `curl -k https://localhost/api/health` shows `"status":"ok"`, and sign-in works in the browser

## 2. First install
```bash
sudo mkdir -p /opt/briha && sudo chown $USER /opt/briha
# copy the project folder to /opt/briha (git clone or scp), then:
cd /opt/briha
cp .env.example .env && chmod 600 .env    # fill in every value (see .env.example)
#   APP_ENV=production, APP_BASE_URL=https://<briha address>, COOKIE_SECURE=true
#   LLM_MODE=openai, DATASOURCE_MODE=rest
mkdir -p deploy/certs backups
# HTTPS certificate: company CA cert, or for a quick start a self-signed one:
openssl req -x509 -nodes -newkey rsa:2048 -days 825 -subj "/CN=briha.example.local" \
  -keyout deploy/certs/briha.key -out deploy/certs/briha.crt
docker compose up -d --build
docker compose ps                     # all services "running"/"healthy"
curl -k https://localhost/api/health  # {"status":"ok",...}
```
The first admin is created from `ADMIN_USERNAME` / `ADMIN_PASSWORD` on first start.

## 3. Update to a new version
```bash
cd /opt/briha && git pull     # or copy new files
docker compose up -d --build  # migrations run automatically
```

## 4. Restore a backup
```bash
docker compose exec -T postgres pg_restore -U briha -d briha --clean < backups/briha-YYYYMMDD-0230.dump
```
Copy `backups/` to a second machine regularly (e.g. nightly rsync).

## 5. Useful commands
| Task | Command |
|---|---|
| Logs | `docker compose logs -f api` |
| Reset a password | `docker compose exec api .venv/bin/python -m app.cli reset-password --username <username>` |
| Restart | `docker compose restart api` |
