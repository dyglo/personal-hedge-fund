"use strict";

const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_IMAGE = "ghcr.io/dyglo/personal-hedge-fund:latest";
const DEFAULT_COMMAND = "chat";
const DEFAULT_WORKSPACE = "/workspace";
const ENV_EXAMPLE_URL = "https://github.com/dyglo/personal-hedge-fund/blob/main/.env.example";

class UserError extends Error {
  constructor(message, exitCode = 1) {
    super(message);
    this.name = "UserError";
    this.exitCode = exitCode;
  }
}

function resolveImage(env = process.env) {
  const override = env.PROPHETAF_IMAGE && env.PROPHETAF_IMAGE.trim();
  return override || DEFAULT_IMAGE;
}

function resolveCliArgs(argv = []) {
  return argv.length > 0 ? [...argv] : [DEFAULT_COMMAND];
}

function resolveEnvPath(cwd) {
  if (/^[A-Za-z]:\\/.test(cwd)) {
    return path.win32.join(cwd, ".env");
  }
  return path.join(cwd, ".env");
}

function ensureEnvFile(cwd, deps) {
  const envPath = resolveEnvPath(cwd);
  if (!deps.existsSync(envPath)) {
    throw new UserError(
      `Missing .env in ${cwd}. Create one in the current directory before running Prophet. Example: ${ENV_EXAMPLE_URL}`,
    );
  }
  return envPath;
}

function stderrMessage(error) {
  if (!error) {
    return "";
  }
  if (typeof error.stderr === "string" && error.stderr.trim()) {
    return error.stderr.trim();
  }
  if (Buffer.isBuffer(error.stderr) && error.stderr.length > 0) {
    return error.stderr.toString("utf8").trim();
  }
  if (error.message) {
    return error.message;
  }
  return String(error);
}

function execDocker(args, deps, options = {}) {
  return deps.execFileSync("docker", args, {
    encoding: "utf8",
    stdio: "pipe",
    ...options,
  });
}

function checkDockerInstalled(deps) {
  try {
    execDocker(["--version"], deps);
  } catch (error) {
    throw new UserError(
      "Docker CLI not found. Install Docker Desktop first: https://www.docker.com/products/docker-desktop/",
    );
  }
}

function checkDockerDaemon(deps) {
  try {
    execDocker(["info"], deps);
  } catch (error) {
    throw new UserError(
      `Docker is installed but not responding. Start Docker Desktop and try again. ${stderrMessage(error)}`.trim(),
    );
  }
}

function imageExists(image, deps) {
  try {
    execDocker(["image", "inspect", image], deps);
    return true;
  } catch (error) {
    if (typeof error.status === "number") {
      return false;
    }
    throw new UserError(`Unable to inspect Docker image ${image}. ${stderrMessage(error)}`.trim());
  }
}

function pullImage(image, deps) {
  deps.console.error(`Prophet image not found. Pulling ${image}...`);
  try {
    execDocker(["pull", image], deps, { stdio: "inherit" });
  } catch (error) {
    throw new UserError(`Failed to pull Docker image ${image}. ${stderrMessage(error)}`.trim());
  }
}

function wantsTty(streams) {
  return Boolean(streams.stdin && streams.stdout && streams.stdin.isTTY && streams.stdout.isTTY);
}

function buildDockerRunArgs({ cwd, envPath, image, cliArgs, tty }) {
  const args = ["run", "--rm"];
  args.push(tty ? "-it" : "-i");
  args.push("--env-file", envPath);
  args.push("-v", `${cwd}:${DEFAULT_WORKSPACE}`);
  args.push("-w", DEFAULT_WORKSPACE);
  args.push(image);
  args.push("hedge-fund", ...resolveCliArgs(cliArgs));
  return args;
}

function runContainer({ cwd, envPath, image, cliArgs, tty }, deps) {
  const args = buildDockerRunArgs({ cwd, envPath, image, cliArgs, tty });
  const result = deps.spawnSync("docker", args, { stdio: "inherit" });

  if (result.error) {
    throw new UserError(`Failed to start Prophet container. ${result.error.message}`.trim());
  }

  if (typeof result.status === "number") {
    return result.status;
  }

  return 1;
}

function createDeps(overrides = {}) {
  return {
    execFileSync: childProcess.execFileSync,
    spawnSync: childProcess.spawnSync,
    existsSync: fs.existsSync,
    console,
    stdin: process.stdin,
    stdout: process.stdout,
    cwd: process.cwd(),
    env: process.env,
    ...overrides,
  };
}

function runCli(overrides = {}) {
  const deps = createDeps(overrides);
  const cwd = overrides.cwd || deps.cwd;
  const env = overrides.env || deps.env;
  const image = resolveImage(env);
  const cliArgs = resolveCliArgs(overrides.argv || []);
  const envPath = ensureEnvFile(cwd, deps);

  deps.console.error("Checking Docker...");
  checkDockerInstalled(deps);
  checkDockerDaemon(deps);
  deps.console.error("Checking Prophet image...");

  if (!imageExists(image, deps)) {
    pullImage(image, deps);
  }

  deps.console.error("Starting Prophet...");
  return runContainer(
    {
      cwd,
      envPath,
      image,
      cliArgs,
      tty: wantsTty(deps),
    },
    deps,
  );
}

module.exports = {
  DEFAULT_COMMAND,
  DEFAULT_IMAGE,
  DEFAULT_WORKSPACE,
  ENV_EXAMPLE_URL,
  UserError,
  buildDockerRunArgs,
  checkDockerDaemon,
  checkDockerInstalled,
  createDeps,
  ensureEnvFile,
  imageExists,
  pullImage,
  resolveCliArgs,
  resolveEnvPath,
  resolveImage,
  runCli,
  runContainer,
  stderrMessage,
  wantsTty,
};
