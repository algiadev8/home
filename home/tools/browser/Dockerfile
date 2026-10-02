FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium xvfb x11vnc novnc websockify openbox socat supervisor \
    ca-certificates fonts-noto-cjk curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 browser && mkdir /profile && chown browser:browser /profile
COPY supervisord.conf /etc/supervisor/conf.d/browser.conf
COPY start-browser.sh /usr/local/bin/start-browser
RUN chmod +x /usr/local/bin/start-browser
ENV DISPLAY=:99
EXPOSE 6080 9223
CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/browser.conf"]
