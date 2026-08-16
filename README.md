# Titatu agents

מוצ׳קה (offer.agent) — Telegram quotes for Titatu.

Primary Telegram user: Sahar Kobi (`6656794957`), owner of Titatu. Operator access: Or Nov (`8818011584`). Pairing lives in the Hermes profile `pairing/telegram-approved.json`.

Dashboard: https://titatu.agents.beosystem.com  
The bot itself does not need a public subdomain. Telegram reaches it with outbound polling.

## Deploy on xCloud (24/7)

Do this once. After that, the Windows PC can stay off.

1. Stop every local copy so Telegram has only one process:
   `hermes -p offer-agent gateway stop`
2. In xCloud on `beo-systems-1`: **+ New Site** → **Custom Docker** → **Docker Compose From Git**.
3. Domain: `titatu.agents.beosystem.com` (DNS A record already points to `212.95.33.243`, DNS only).
4. Connect GitHub `ceo7815/titatu-agents`, branch `master`, compose file `docker-compose.yml`.
5. Port detection: primary service port **8080** (dashboard). Do not map port 8642.
6. Enable **Environment File** and paste values from `.env.example` (same secrets as the local Hermes profile `.env`, `wp.env`, dashboard `.env.local`, and `.ops_secret`).
7. Turn on **auto-deploy on push** and enable HTTPS.
8. After the first deploy, open the dashboard URL and send מוצ׳קה a Telegram message.

Later: fix in Cursor → commit → push to `master` → xCloud redeploys.
