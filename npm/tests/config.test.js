"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const configStore = require("../lib/config");

function withTempHome(t) {
  const originalHomedir = os.homedir;
  const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "prophetaf-config-"));
  os.homedir = () => tempHome;
  t.after(() => {
    os.homedir = originalHomedir;
    fs.rmSync(tempHome, { recursive: true, force: true });
  });
  return tempHome;
}

test("configExists returns false when ~/.prophet/config.json is absent", t => {
  withTempHome(t);

  assert.equal(configStore.configExists(), false);
});

test("configExists returns true when config file exists", t => {
  const tempHome = withTempHome(t);
  fs.mkdirSync(path.join(tempHome, ".prophet"), { recursive: true });
  fs.writeFileSync(
    path.join(tempHome, ".prophet", "config.json"),
    JSON.stringify({ device_token: "device-123", onboarded: true }),
    "utf8",
  );

  assert.equal(configStore.configExists(), true);
});

test("isConfigValid returns false when config is null", () => {
  assert.equal(configStore.isConfigValid(null), false);
});

test("isConfigValid returns false when device_token is missing", () => {
  assert.equal(configStore.isConfigValid({ onboarded: true }), false);
});

test("isConfigValid returns false when onboarded is false", () => {
  assert.equal(configStore.isConfigValid({ device_token: "device-123", onboarded: false }), false);
});

test("isConfigValid returns true for a complete config object", () => {
  assert.equal(configStore.isConfigValid({ device_token: "device-123", onboarded: true }), true);
});

test("readConfig returns null gracefully when file does not exist", t => {
  withTempHome(t);

  assert.equal(configStore.readConfig(), null);
});

test("writeConfig creates the ~/.prophet directory when it does not exist", t => {
  const tempHome = withTempHome(t);

  const saved = configStore.writeConfig({
    device_token: "device-123",
    display_name: "Tafar",
    onboarded: true,
  });

  assert.equal(saved, true);
  assert.equal(fs.existsSync(path.join(tempHome, ".prophet")), true);
  assert.equal(fs.existsSync(path.join(tempHome, ".prophet", "config.json")), true);
});
