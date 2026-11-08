FROM debian:bookworm-slim
# Every package below is required by supervisord.conf or start-browser.sh:
# chromium (browser), xvfb (virtual screen), openbox (window manager so tabs
# render), x11vnc + novnc + websockify (noVNC view), socat (CDP proxy),
# supervisor (process supervision), fonts-noto-cjk (Japanese page rendering).
# ca-certificates is needed for HTTPS pages; curl is not used by the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium xvfb x11vnc novnc websockify openbox socat supervisor \
    ca-certificates fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 browser && mkdir /profile && chown browser:browser /profile
COPY supervisord.conf /etc/supervisor/conf.d/browser.conf
COPY start-browser.sh /usr/local/bin/start-browser
RUN chmod +x /usr/local/bin/start-browser
ENV DISPLAY=:99
EXPOSE 6080 9223
CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/browser.conf"]
