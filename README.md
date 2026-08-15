# Titatu agents

מוצ׳קה (offer.agent) — Telegram quotes for Titatu.

## Deploy on xCloud (24/7)

1. Stop the local Windows gateway so Telegram has only one bot process:
   `hermes -p offer-agent gateway stop`
2. In xCloud: **+ New Site** on `beo-systems-1` → **Custom Docker** → **Docker Compose From Git**.
3. Connect GitHub `ceo7815/titatu-agents`, branch `main`, compose file `docker-compose.yml`.
4. Enable **Environment File** and paste the keys from `.env.example` (same values as the local Hermes profile `.env` + `wp.env`).
5. Turn on **auto-deploy on push**.
6. After the first deploy, send מוצ׳קה a Telegram message. Pair if asked.

Later: fix in Cursor → commit → push to `main` → xCloud redeploys.
