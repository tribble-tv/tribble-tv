FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget curl ca-certificates bzip2 libgtk-3-0 libdbus-glib-1-2 \
        libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libxss1 \
        libxtst6 libpci3 libdrm2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m camoufox fetch
COPY backend ./backend
ENV FLASK_APP=backend.app:app
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
