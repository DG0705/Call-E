FROM debian:bullseye-slim

# Bullseye is archived; point apt at archive.debian.org for reproducible dev builds.
# Archived security updates were merged into the main archive, so drop the
# separate security suite.
RUN sed -i 's|deb.debian.org|archive.debian.org|g' /etc/apt/sources.list \
    && sed -i '/bullseye-security/d' /etc/apt/sources.list \
    && sed -i '/bullseye-updates/d' /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends asterisk \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/lib/asterisk/sounds

COPY telephony/asterisk/config/ /etc/asterisk/
COPY telephony/asterisk/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 5060/udp 8088

# The entrypoint injects local secrets (from env) into the placeholder config,
# then execs Asterisk in the foreground.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
