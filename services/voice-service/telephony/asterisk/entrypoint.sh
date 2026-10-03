#!/bin/sh
# Inject local secrets into the baked-in Asterisk config at container start.
#
# Tracked config files ship with CHANGE_ME_* placeholders so no credential is
# ever committed. The real values come from the container environment (fed by
# the untracked local .env through docker-compose) and are substituted here,
# immediately before Asterisk launches. Media/RTP/SIP transport settings are
# never rewritten — only the two auth passwords.
#
# Passwords are expected to be simple alphanumeric secrets (no |, & or \).
set -eu

ARI_CONF=/etc/asterisk/ari.conf
PJSIP_CONF=/etc/asterisk/pjsip.conf

: "${ASTERISK_PASSWORD:?ASTERISK_PASSWORD must be set for ARI auth (see .env)}"
: "${DEV_PHONE_SIP_PASSWORD:?DEV_PHONE_SIP_PASSWORD must be set for the dev softphone (see .env)}"

sed -i "s|CHANGE_ME_ARI_LOCAL_ONLY|${ASTERISK_PASSWORD}|g" "$ARI_CONF"
sed -i "s|CHANGE_ME_LOCAL_ONLY|${DEV_PHONE_SIP_PASSWORD}|g" "$PJSIP_CONF"

exec asterisk -f -vvv
