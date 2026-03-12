"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  detectImagePaths,
  readImageAsBase64,
  stripImagePathsFromMessage,
  validateImageFile,
} = require("../lib/image_handler");

const ONE_BY_ONE_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO6W6p0AAAAASUVORK5CYII=";

function withTempDir(t) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "prophetaf-image-handler-"));
  t.after(() => {
    if (process.cwd() === tempDir) {
      process.chdir(os.tmpdir());
    }
    fs.rmSync(tempDir, { recursive: true, force: true });
  });
  return tempDir;
}

function withCwd(t, cwd) {
  const originalCwd = process.cwd();
  process.chdir(cwd);
  t.after(() => {
    process.chdir(originalCwd);
  });
}

function writePng(filePath, base64 = ONE_BY_ONE_PNG) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, Buffer.from(base64, "base64"));
}

function writePngHeader(filePath, width, height) {
  const header = Buffer.alloc(24);
  Buffer.from("89504e470d0a1a0a", "hex").copy(header, 0);
  header.writeUInt32BE(width, 16);
  header.writeUInt32BE(height, 20);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, header);
}

test("detectImagePaths finds Windows absolute paths", () => {
  assert.deepEqual(
    detectImagePaths("analyse C:\\charts\\xauusd.png"),
    ["C:\\charts\\xauusd.png"],
  );
});

test("detectImagePaths finds Unix absolute paths", () => {
  assert.deepEqual(
    detectImagePaths("analyse /tmp/charts/xauusd.png now"),
    ["/tmp/charts/xauusd.png"],
  );
});

test("detectImagePaths returns empty array for text-only messages", () => {
  assert.deepEqual(detectImagePaths("what is the bias on gold today"), []);
});

test("detectImagePaths resolves quoted relative paths with spaces", t => {
  const tempDir = withTempDir(t);
  withCwd(t, tempDir);

  assert.deepEqual(
    detectImagePaths('analyse "./charts/gold chart.png"'),
    [path.join(tempDir, "charts", "gold chart.png")],
  );
});

test("validateImageFile returns a missing-file error", t => {
  const tempDir = withTempDir(t);
  const filePath = path.join(tempDir, "missing.png");

  assert.deepEqual(validateImageFile(filePath), {
    valid: false,
    error: `Image not found or format not supported: ${filePath}`,
  });
});

test("validateImageFile rejects unsupported extensions", t => {
  const tempDir = withTempDir(t);
  const filePath = path.join(tempDir, "chart.pdf");
  fs.writeFileSync(filePath, "pdf");

  assert.deepEqual(validateImageFile(filePath), {
    valid: false,
    error: `Image not found or format not supported: ${filePath}`,
  });
});

test("stripImagePathsFromMessage removes paths and tidies whitespace", () => {
  const filePath = "C:\\charts\\xauusd_h1.png";

  assert.equal(
    stripImagePathsFromMessage(`analyse this setup ${filePath} what is the bias?`, [filePath]),
    "analyse this setup - what is the bias?",
  );
});

test("readImageAsBase64 returns raw base64 for a valid png", t => {
  const tempDir = withTempDir(t);
  const filePath = path.join(tempDir, "chart.png");
  writePng(filePath);

  const encoded = readImageAsBase64(filePath);

  assert.ok(encoded.length > 0);
  assert.doesNotMatch(encoded, /^data:/);
});

test("validateImageFile rejects files over 5MB before reading image data", t => {
  const tempDir = withTempDir(t);
  const filePath = path.join(tempDir, "large.png");
  fs.writeFileSync(filePath, Buffer.alloc((5 * 1024 * 1024) + 1));

  assert.deepEqual(validateImageFile(filePath), {
    valid: false,
    error: "Chart image exceeds 5MB limit. Please reduce the screenshot resolution and try again.",
  });
});

test("validateImageFile rejects images above the dimension limit", t => {
  const tempDir = withTempDir(t);
  const filePath = path.join(tempDir, "too-wide.png");
  writePngHeader(filePath, 9001, 1000);

  assert.deepEqual(validateImageFile(filePath), {
    valid: false,
    error: "Chart image exceeds 8000x8000 pixel limit. Please reduce the screenshot resolution and try again.",
  });
});

test("validateImageFile returns media type and size for a valid png", t => {
  const tempDir = withTempDir(t);
  const filePath = path.join(tempDir, "chart.png");
  writePng(filePath);

  assert.deepEqual(validateImageFile(filePath), {
    valid: true,
    mediaType: "image/png",
    sizeBytes: fs.statSync(filePath).size,
  });
});
