"use strict";

const fs = require("node:fs");
const path = require("node:path");

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_IMAGE_DIMENSION = 8000;

const MEDIA_TYPES = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

const QUOTED_PATH_PATTERN = /(["'])((?:[A-Za-z]:\\|\\\\|\/|\.{1,2}[\\/])[^"'\r\n]*?\.(?:png|jpe?g|webp))\1/gi;
const UNQUOTED_PATH_PATTERN = /(?:^|[\s(])((?:[A-Za-z]:\\|\\\\|\/|\.{1,2}[\\/])[^\s"'<>|?*\r\n]+?\.(?:png|jpe?g|webp))(?=$|[\s),.;!?])/gi;

function isWindowsAbsolutePath(value) {
  return /^[A-Za-z]:\\/.test(value) || /^\\\\/.test(value);
}

function isUnixAbsolutePath(value) {
  return /^\//.test(value);
}

function supportedExtension(filePath) {
  const extension = path.extname(filePath || "").toLowerCase();
  return MEDIA_TYPES[extension] || null;
}

function normalizeCandidatePath(filePath, cwd = process.cwd()) {
  const value = String(filePath || "").trim();
  if (!value) {
    return "";
  }
  if (isWindowsAbsolutePath(value)) {
    return path.win32.normalize(value);
  }
  if (isUnixAbsolutePath(value)) {
    return path.posix.normalize(value);
  }
  return path.resolve(cwd, value);
}

function candidateKey(filePath) {
  if (!filePath) {
    return "";
  }
  return process.platform === "win32" ? filePath.toLowerCase() : filePath;
}

function collectMatches(message, cwd = process.cwd()) {
  const text = String(message || "");
  const matches = [];

  const pushMatch = (raw, candidatePath, index) => {
    const normalizedPath = normalizeCandidatePath(candidatePath, cwd);
    if (!normalizedPath || !supportedExtension(candidatePath)) {
      return;
    }
    matches.push({
      index,
      raw,
      path: normalizedPath,
    });
  };

  let match;
  while ((match = QUOTED_PATH_PATTERN.exec(text)) !== null) {
    pushMatch(match[0], match[2], match.index);
  }

  while ((match = UNQUOTED_PATH_PATTERN.exec(text)) !== null) {
    const raw = match[1];
    const offset = match[0].lastIndexOf(raw);
    pushMatch(raw, raw, match.index + offset);
  }

  matches.sort((left, right) => left.index - right.index || right.raw.length - left.raw.length);

  const deduped = [];
  const seen = new Set();
  for (const entry of matches) {
    const key = candidateKey(entry.path);
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(entry);
  }

  return deduped;
}

function detectImagePaths(message) {
  return collectMatches(message).map(entry => entry.path);
}

function readChunk(fd, offset, length) {
  const buffer = Buffer.alloc(length);
  const bytesRead = fs.readSync(fd, buffer, 0, length, offset);
  return buffer.subarray(0, bytesRead);
}

function parsePngDimensions(fd) {
  const header = readChunk(fd, 0, 24);
  if (header.length < 24 || header.toString("hex", 0, 8) !== "89504e470d0a1a0a") {
    return null;
  }
  return {
    width: header.readUInt32BE(16),
    height: header.readUInt32BE(20),
  };
}

function parseJpegDimensions(fd, fileSize) {
  const markerBytes = new Set([
    0xC0, 0xC1, 0xC2, 0xC3,
    0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB,
    0xCD, 0xCE, 0xCF,
  ]);
  const signature = readChunk(fd, 0, 2);
  if (signature.length < 2 || signature[0] !== 0xFF || signature[1] !== 0xD8) {
    return null;
  }

  let position = 2;
  while (position < fileSize) {
    const marker = readChunk(fd, position, 2);
    if (marker.length < 2) {
      return null;
    }
    if (marker[0] !== 0xFF) {
      return null;
    }

    const code = marker[1];
    position += 2;

    if (code === 0xD8 || code === 0x01 || (code >= 0xD0 && code <= 0xD7)) {
      continue;
    }
    if (code === 0xD9 || code === 0xDA) {
      break;
    }

    const lengthBytes = readChunk(fd, position, 2);
    if (lengthBytes.length < 2) {
      return null;
    }
    const segmentLength = lengthBytes.readUInt16BE(0);
    if (segmentLength < 2) {
      return null;
    }

    if (markerBytes.has(code)) {
      const frame = readChunk(fd, position + 2, 5);
      if (frame.length < 5) {
        return null;
      }
      return {
        width: frame.readUInt16BE(3),
        height: frame.readUInt16BE(1),
      };
    }

    position += segmentLength;
  }

  return null;
}

function parseWebpDimensions(fd) {
  const header = readChunk(fd, 0, 30);
  if (
    header.length < 16
    || header.toString("ascii", 0, 4) !== "RIFF"
    || header.toString("ascii", 8, 12) !== "WEBP"
  ) {
    return null;
  }

  const chunkType = header.toString("ascii", 12, 16);
  if (chunkType === "VP8X") {
    if (header.length < 30) {
      return null;
    }
    return {
      width: 1 + header.readUIntLE(24, 3),
      height: 1 + header.readUIntLE(27, 3),
    };
  }

  if (chunkType === "VP8L") {
    if (header.length < 25 || header[20] !== 0x2F) {
      return null;
    }
    const bits = header.readUInt32LE(21);
    return {
      width: (bits & 0x3FFF) + 1,
      height: ((bits >> 14) & 0x3FFF) + 1,
    };
  }

  if (chunkType === "VP8 ") {
    if (header.length < 30 || header[23] !== 0x9D || header[24] !== 0x01 || header[25] !== 0x2A) {
      return null;
    }
    return {
      width: header.readUInt16LE(26) & 0x3FFF,
      height: header.readUInt16LE(28) & 0x3FFF,
    };
  }

  return null;
}

function readImageDimensions(filePath, mediaType) {
  let fd;
  try {
    fd = fs.openSync(filePath, "r");
    const fileSize = fs.fstatSync(fd).size;
    if (mediaType === "image/png") {
      return parsePngDimensions(fd);
    }
    if (mediaType === "image/jpeg") {
      return parseJpegDimensions(fd, fileSize);
    }
    if (mediaType === "image/webp") {
      return parseWebpDimensions(fd);
    }
    return null;
  } finally {
    if (fd !== undefined) {
      fs.closeSync(fd);
    }
  }
}

function validateImageFile(filePath) {
  const normalizedPath = normalizeCandidatePath(filePath);
  const mediaType = supportedExtension(normalizedPath);

  if (!mediaType) {
    return {
      valid: false,
      error: `Image not found or format not supported: ${filePath}`,
    };
  }

  let stats;
  try {
    stats = fs.statSync(normalizedPath);
  } catch {
    return {
      valid: false,
      error: `Image not found or format not supported: ${filePath}`,
    };
  }

  if (!stats.isFile()) {
    return {
      valid: false,
      error: `Image not found or format not supported: ${filePath}`,
    };
  }

  if (stats.size > MAX_IMAGE_BYTES) {
    return {
      valid: false,
      error: "Chart image exceeds 5MB limit. Please reduce the screenshot resolution and try again.",
    };
  }

  let dimensions;
  try {
    dimensions = readImageDimensions(normalizedPath, mediaType);
  } catch {
    return {
      valid: false,
      error: "Could not read image file. Check the file path and try again.",
    };
  }

  if (!dimensions) {
    return {
      valid: false,
      error: "Could not read image file. Check the file path and try again.",
    };
  }

  if (dimensions.width > MAX_IMAGE_DIMENSION || dimensions.height > MAX_IMAGE_DIMENSION) {
    return {
      valid: false,
      error: "Chart image exceeds 8000x8000 pixel limit. Please reduce the screenshot resolution and try again.",
    };
  }

  return {
    valid: true,
    mediaType,
    sizeBytes: stats.size,
  };
}

function readImageAsBase64(filePath) {
  const normalizedPath = normalizeCandidatePath(filePath);
  const base64 = fs.readFileSync(normalizedPath).toString("base64").replace(/^data:[^,]+,/, "").trim();
  if (!base64) {
    throw new Error("Image file is empty");
  }
  return base64;
}

function cleanupMessage(text) {
  return String(text || "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([,.;!?])/g, "$1")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")")
    .replace(/\s+-\s+(for|with|and|or|to)\b/gi, " $1")
    .replace(/\s+-\s+/g, " - ")
    .trim();
}

function stripImagePathsFromMessage(message, paths) {
  const candidates = collectMatches(message);
  const targets = new Set((paths || []).map(candidateKey));
  let output = String(message || "");

  for (const entry of [...candidates].reverse()) {
    if (!targets.has(candidateKey(entry.path))) {
      continue;
    }
    const start = entry.index;
    const end = start + entry.raw.length;
    const previous = output.slice(0, start);
    const next = output.slice(end);
    const leftChar = previous.trimEnd().slice(-1);
    const rightChar = next.trimStart().slice(0, 1);
    const replacement = leftChar && rightChar && /[A-Za-z0-9]/.test(leftChar) && /[A-Za-z0-9]/.test(rightChar)
      ? " - "
      : " ";
    output = `${previous}${replacement}${next}`;
  }

  return cleanupMessage(output);
}

module.exports = {
  MAX_IMAGE_BYTES,
  MAX_IMAGE_DIMENSION,
  detectImagePaths,
  readImageAsBase64,
  stripImagePathsFromMessage,
  validateImageFile,
};
