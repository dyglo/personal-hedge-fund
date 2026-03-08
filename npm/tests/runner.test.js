"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DEFAULT_IMAGE,
  DEFAULT_WORKSPACE,
  ENV_EXAMPLE_URL,
  UserError,
  buildDockerRunArgs,
  ensureEnvFile,
  resolveCliArgs,
  resolveImage,
  runCli,
} = require("../lib/runner");

function createConsole() {
  return {
    messages: [],
    error(message) {
      this.messages.push(message);
    },
  };
}

test("resolveImage uses env override when present", () => {
  assert.equal(resolveImage({ PROPHETAF_IMAGE: "ghcr.io/example/custom:1.0.0" }), "ghcr.io/example/custom:1.0.0");
  assert.equal(resolveImage({}), DEFAULT_IMAGE);
});

test("resolveCliArgs defaults to chat and preserves passthrough args", () => {
  assert.deepEqual(resolveCliArgs([]), ["chat"]);
  assert.deepEqual(resolveCliArgs(["risk", "--pair", "XAUUSD"]), ["risk", "--pair", "XAUUSD"]);
});

test("ensureEnvFile throws a helpful error when .env is missing", () => {
  assert.throws(
    () =>
      ensureEnvFile("D:\\trader", {
        existsSync() {
          return false;
        },
      }),
    (error) => {
      assert.ok(error instanceof UserError);
      assert.match(error.message, /Missing \.env/);
      assert.match(error.message, new RegExp(ENV_EXAMPLE_URL.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
      return true;
    },
  );
});

test("buildDockerRunArgs mounts the workspace and launches hedge-fund", () => {
  const args = buildDockerRunArgs({
    cwd: "D:\\projects\\new",
    envPath: "D:\\projects\\new\\.env",
    image: DEFAULT_IMAGE,
    cliArgs: ["scan", "--pair", "XAUUSD"],
    tty: true,
  });

  assert.deepEqual(args, [
    "run",
    "--rm",
    "-it",
    "--env-file",
    "D:\\projects\\new\\.env",
    "-v",
    `D:\\projects\\new:${DEFAULT_WORKSPACE}`,
    "-w",
    DEFAULT_WORKSPACE,
    DEFAULT_IMAGE,
    "hedge-fund",
    "scan",
    "--pair",
    "XAUUSD",
  ]);
});

test("runCli pulls the image when missing and defaults to chat", () => {
  const calls = [];
  const fakeConsole = createConsole();

  const exitCode = runCli({
    cwd: "D:\\projects\\new",
    env: {},
    argv: [],
    console: fakeConsole,
    stdin: { isTTY: false },
    stdout: { isTTY: false },
    existsSync(filePath) {
      return filePath === "D:\\projects\\new\\.env";
    },
    execFileSync(command, args) {
      calls.push({ type: "exec", command, args });
      if (args[0] === "image" && args[1] === "inspect") {
        const error = new Error("missing image");
        error.status = 1;
        throw error;
      }
      return "";
    },
    spawnSync(command, args) {
      calls.push({ type: "spawn", command, args });
      return { status: 0 };
    },
  });

  assert.equal(exitCode, 0);
  assert.deepEqual(
    calls.map((call) => call.args),
    [
      ["--version"],
      ["info"],
      ["image", "inspect", DEFAULT_IMAGE],
      ["pull", DEFAULT_IMAGE],
      [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "D:\\projects\\new\\.env",
        "-v",
        `D:\\projects\\new:${DEFAULT_WORKSPACE}`,
        "-w",
        DEFAULT_WORKSPACE,
        DEFAULT_IMAGE,
        "hedge-fund",
        "chat",
      ],
    ],
  );
  assert.deepEqual(fakeConsole.messages, [
    "Checking Docker...",
    "Checking Prophet image...",
    `Prophet image not found. Pulling ${DEFAULT_IMAGE}...`,
    "Starting Prophet...",
  ]);
});

test("runCli passes through explicit commands without pulling when image exists", () => {
  const calls = [];

  const exitCode = runCli({
    cwd: "D:\\projects\\new",
    env: { PROPHETAF_IMAGE: "ghcr.io/acme/prophet:test" },
    argv: ["risk", "--pair", "XAUUSD", "--sl", "15", "--risk", "1"],
    console: createConsole(),
    stdin: { isTTY: true },
    stdout: { isTTY: true },
    existsSync() {
      return true;
    },
    execFileSync(command, args) {
      calls.push({ type: "exec", command, args });
      return "";
    },
    spawnSync(command, args) {
      calls.push({ type: "spawn", command, args });
      return { status: 0 };
    },
  });

  assert.equal(exitCode, 0);
  assert.deepEqual(calls[calls.length - 1], {
    type: "spawn",
    command: "docker",
    args: [
      "run",
      "--rm",
      "-it",
      "--env-file",
      "D:\\projects\\new\\.env",
      "-v",
      `D:\\projects\\new:${DEFAULT_WORKSPACE}`,
      "-w",
      DEFAULT_WORKSPACE,
      "ghcr.io/acme/prophet:test",
      "hedge-fund",
      "risk",
      "--pair",
      "XAUUSD",
      "--sl",
      "15",
      "--risk",
      "1",
    ],
  });
});

test("runCli surfaces a clear Docker daemon error", () => {
  assert.throws(
    () =>
      runCli({
        cwd: "D:\\projects\\new",
        env: {},
        argv: [],
        console: createConsole(),
        stdin: { isTTY: false },
        stdout: { isTTY: false },
        existsSync() {
          return true;
        },
        execFileSync(command, args) {
          if (args[0] === "info") {
            const error = new Error("Cannot connect");
            error.stderr = "daemon offline";
            throw error;
          }
          return "";
        },
        spawnSync() {
          throw new Error("should not run container");
        },
      }),
    (error) => {
      assert.ok(error instanceof UserError);
      assert.match(error.message, /Docker is installed but not responding/);
      assert.match(error.message, /daemon offline/);
      return true;
    },
  );
});
