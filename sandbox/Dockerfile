FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify fluxbox xdotool scrot \
        firefox-esr fonts-dejavu-core ca-certificates curl python3 bash procps \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

COPY api.py /opt/sandbox/api.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Runs as root inside the container. The container is the boundary, not the user.
ENV DISPLAY=:1 HOME=/root SCREEN_SIZE=1280x800

EXPOSE 6080 8001
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]