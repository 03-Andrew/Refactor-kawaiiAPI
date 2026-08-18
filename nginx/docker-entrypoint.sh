#!/bin/sh
set -e

DOMAIN="${DOMAIN:-test-booking.dreww.space}"
CERT_PATH="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
CONF_DIR="/etc/nginx/conf.d"

if [ -f "$CERT_PATH" ]; then
    echo "Certificate found for ${DOMAIN}, using SSL config"
    cp /nginx-templates/app.conf.ssl "$CONF_DIR/default.conf"
else
    echo "No certificate found for ${DOMAIN}, using bootstrap config"
    cp /nginx-templates/app.conf.bootstrap "$CONF_DIR/default.conf"
fi

exec nginx -g "daemon off;"