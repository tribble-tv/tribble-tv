import express from "express";
import WebTorrent from "webtorrent";
import path from "path";

const app = express();
const client = new WebTorrent();
const PORT = process.env.TORRENT_PORT || 9119;
const DOWNLOAD_PATH = process.env.TORRENT_DOWNLOAD_PATH || "/tmp/torrents";
const MAX_TORRENTS = parseInt(process.env.MAX_TORRENTS || "10", 10);

// Map: magnetOrHash -> torrent object
const activeTorrents = new Map();

function pickVideoFile(torrent) {
  const videoExts = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m4v", ".mpg", ".mpeg"];
  const files = torrent.files.filter(f =>
    videoExts.some(ext => f.name.toLowerCase().endsWith(ext))
  );
  if (files.length === 0) return torrent.files[0];
  return files.reduce((a, b) => (a.length > b.length ? a : b));
}

function normalizeMagnet(raw) {
  if (raw.startsWith("magnet:")) return raw;
  if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
  // Bare infohash
  return `magnet:?xt=urn:btih:${raw}`;
}

function ensureTorrent(magnet) {
  return new Promise((resolve, reject) => {
    const uri = normalizeMagnet(magnet);
    const existing = activeTorrents.get(uri);
    if (existing) {
      return resolve(existing);
    }

    // Enforce max concurrent torrents
    if (activeTorrents.size >= MAX_TORRENTS) {
      // Remove the oldest torrent
      const [oldKey, oldTorrent] = activeTorrents.entries().next().value;
      oldTorrent.destroy();
      activeTorrents.delete(oldKey);
    }

    client.add(uri, { path: DOWNLOAD_PATH }, torrent => {
      activeTorrents.set(uri, torrent);
      torrent.on("error", err => {
        console.error(`Torrent error [${uri}]:`, err.message);
        activeTorrents.delete(uri);
      });
      resolve(torrent);
    });

    client.on("error", err => {
      reject(err);
    });
  });
}

// GET /stream?magnet=<magnet_or_hash>[&file=<filename>]
app.get("/stream", async (req, res) => {
  const magnet = req.query.magnet;
  if (!magnet) {
    return res.status(400).json({ error: "magnet query parameter required" });
  }

  let torrent;
  try {
    torrent = await ensureTorrent(magnet);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }

  const file = req.query.file
    ? torrent.files.find(f => f.name === req.query.file) || pickVideoFile(torrent)
    : pickVideoFile(torrent);

  if (!file) {
    return res.status(404).json({ error: "No suitable video file found in torrent" });
  }

  const fileSize = file.length;
  const rangeHeader = req.headers.range;

  res.setHeader("Accept-Ranges", "bytes");
  res.setHeader("Content-Type", _mimeType(file.name));
  res.setHeader("Content-Disposition", `inline; filename="${file.name}"`);

  if (rangeHeader) {
    const [startStr, endStr] = rangeHeader.replace(/bytes=/, "").split("-");
    const start = parseInt(startStr, 10);
    const end = endStr ? parseInt(endStr, 10) : fileSize - 1;
    const chunkSize = end - start + 1;

    res.status(206);
    res.setHeader("Content-Range", `bytes ${start}-${end}/${fileSize}`);
    res.setHeader("Content-Length", chunkSize);

    const stream = file.createReadStream({ start, end });
    stream.pipe(res);
    stream.on("error", err => {
      if (!res.headersSent) res.status(500).end();
    });
  } else {
    res.setHeader("Content-Length", fileSize);
    const stream = file.createReadStream();
    stream.pipe(res);
    stream.on("error", err => {
      if (!res.headersSent) res.status(500).end();
    });
  }
});

// GET /info?magnet=<magnet_or_hash>
app.get("/info", async (req, res) => {
  const magnet = req.query.magnet;
  if (!magnet) {
    return res.status(400).json({ error: "magnet query parameter required" });
  }

  let torrent;
  try {
    torrent = await ensureTorrent(magnet);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }

  const videoFile = pickVideoFile(torrent);
  res.json({
    name: torrent.name,
    infoHash: torrent.infoHash,
    magnetURI: torrent.magnetURI,
    length: torrent.length,
    progress: torrent.progress,
    downloadSpeed: torrent.downloadSpeed,
    uploadSpeed: torrent.uploadSpeed,
    numPeers: torrent.numPeers,
    files: torrent.files.map(f => ({
      name: f.name,
      length: f.length,
      progress: f.progress,
    })),
    videoFile: videoFile
      ? { name: videoFile.name, length: videoFile.length, progress: videoFile.progress }
      : null,
  });
});

// GET /status — lista todos os torrents ativos
app.get("/status", (req, res) => {
  const torrents = [];
  for (const [uri, t] of activeTorrents.entries()) {
    torrents.push({
      magnetURI: t.magnetURI || uri,
      name: t.name,
      infoHash: t.infoHash,
      progress: t.progress,
      downloadSpeed: t.downloadSpeed,
      numPeers: t.numPeers,
      done: t.done,
    });
  }
  res.json({ active: torrents.length, maxTorrents: MAX_TORRENTS, torrents });
});

// DELETE /torrent?magnet=<magnet_or_hash> — remove torrent da memória
app.delete("/torrent", (req, res) => {
  const magnet = req.query.magnet;
  if (!magnet) return res.status(400).json({ error: "magnet required" });
  const uri = normalizeMagnet(magnet);
  const torrent = activeTorrents.get(uri);
  if (!torrent) return res.status(404).json({ error: "Torrent not found" });
  torrent.destroy(() => {
    activeTorrents.delete(uri);
    res.json({ ok: true });
  });
});

// GET /health
app.get("/health", (req, res) => {
  res.json({ status: "ok", activeTorrents: activeTorrents.size });
});

function _mimeType(filename) {
  const ext = path.extname(filename).toLowerCase();
  const map = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".ts": "video/mp2t",
    ".m4v": "video/mp4",
    ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg",
  };
  return map[ext] || "application/octet-stream";
}

app.listen(PORT, () => {
  console.log(`Tribble torrent-service running on :${PORT}`);
});
