FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify fluxbox xdotool scrot \
        firefox-esr fonts-dejavu-core ca-certificates procps bash \
    && rm -rf /var/lib/apt/lists/*

# The desktop and all apps run as an ordinary user, not root.
RUN useradd -m -u 1000 agent

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER agent
ENV DISPLAY=:1 HOME=/home/agent

EXPOSE 6080
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]