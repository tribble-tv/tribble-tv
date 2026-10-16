FROM node:20-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

COPY package.json ./
RUN npm install --omit=dev

COPY server.js ./

ENV TORRENT_PORT=9119
ENV TORRENT_DOWNLOAD_PATH=/tmp/torrents
ENV MAX_TORRENTS=10

EXPOSE 9119

CMD ["node", "server.js"]
