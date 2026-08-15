#!/bin/sh
set -eu

DATA="${HERMES_HOME:-/opt/data}"
PROFILE="$DATA/profiles/offer-agent"
SRC="/opt/offer-agent"

mkdir -p "$PROFILE/plugins" "$PROFILE/cache/intake" "$PROFILE/pairing"

if [ ! -f "$PROFILE/profile.yaml" ]; then
  printf 'description: Titatu offer.agent (Moczka)\n' > "$PROFILE/profile.yaml"
fi

rm -rf "$PROFILE/plugins/titatu-wp-bridge"
cp -a "$SRC/plugins/titatu-wp-bridge" "$PROFILE/plugins/"
cp "$SRC/SOUL.md" "$PROFILE/SOUL.md"
cp /opt/deploy/config.yaml "$PROFILE/config.yaml"

ENVFILE="$PROFILE/.env"
: > "$ENVFILE"
for key in OPENAI_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_ALLOWED_USERS \
  WP_URL WP_USERNAME WP_APP_PASSWORD WP_ORIGIN_URL WP_ORIGIN_HOST \
  GATEWAY_ALLOW_ALL_USERS; do
  eval "val=\${$key-}"
  if [ -n "$val" ]; then
    printf '%s=%s\n' "$key" "$val" >> "$ENVFILE"
  fi
done

exec hermes -p offer-agent gateway run
