FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends asterisk \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/lib/asterisk/sounds

COPY telephony/asterisk/config/ /etc/asterisk/

EXPOSE 5060/udp 8088

CMD ["asterisk", "-f", "-vvv"]
