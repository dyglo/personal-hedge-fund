"use strict";

const { name: PACKAGE_NAME, version: CLI_VERSION } = require("../package.json");
const https = require("node:https");
const readline = require("node:readline/promises");

const PROPHET_BANNER = `
  ██████╗ ██████╗  ██████╗ ██████╗ ██╗  ██╗███████╗████████╗
  ██╔══██╗██╔══██╗██╔═══██╗██╔══██╗██║  ██║██╔════╝╚══██╔══╝
  ██████╔╝██████╔╝██║   ██║██████╔╝███████║█████╗     ██║
  ██╔═══╝ ██╔══██╗██║   ██║██╔═══╝ ██╔══██║██╔══╝     ██║
  ██║     ██║  ██║╚██████╔╝██║     ██║  ██║███████╗   ██║
  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝  ╚═╝╚══════╝   ╚═╝

  Personal AI Trading Assistant  |  v${CLI_VERSION}  |  Cloud Edition
`;

const BACKEND_BASE_URL = "https://prophet-wwxjsbvhoa-uc.a.run.app";
const NPM_REGISTRY_BASE_URL = "https://registry.npmjs.org";
const SPINNER_FRAMES = ["◐", "◓", "◑", "◒"];
const UPDATE_BOX_INNER_WIDTH = 53;
const UPDATE_CHECK_TIMEOUT_MS = 1200;
const ANSI_RESET = "\u001b[0m";
const ANSI_BOLD = "\u001b[1m";
const ANSI_DIM = "\u001b[2m";
const ANSI_CYAN = "\u001b[36m";
const ANSI_BLUE = "\u001b[34m";
const ANSI_GREEN = "\u001b[32m";
const ANSI_YELLOW = "\u001b[33m";
const ANSI_MAGENTA = "\u001b[35m";
const ANSI_WHITE = "\u001b[37m";
const ANSI_GRAY = "\u001b[90m";
const ANSI_STRIP_PATTERN = /\u001b\[[0-9;]*m/g;
const WEB_SEARCH_HINT_PATTERN = /\b(news|headline|headlines|today|latest|current events|macro|search|web|cpi|nfp|fomc|fed|tariff|geopolitical)\b/i;

const LABEL_SETS = {
  scan: [
    "Sweeping the watchlist...",
    "Scanning market structure...",
    "Checking confluence zones...",
    "Reading recent candles...",
    "Sizing up momentum...",
    "Reviewing breakout pressure...",
    "Watching session overlap...",
    "Measuring structure quality...",
    "Ranking setup strength...",
    "Filtering noisy pairs...",
  ],
  bias: [
    "Reading directional flow...",
    "Mapping higher-timeframe bias...",
    "Checking session posture...",
    "Measuring trend pressure...",
    "Reviewing swing structure...",
    "Tracing liquidity path...",
    "Weighing continuation odds...",
    "Scanning directional clues...",
    "Balancing bullish and bearish cases...",
    "Locking in market bias...",
  ],
  risk: [
    "Calibrating position size...",
    "Sizing the trade...",
    "Checking risk exposure...",
    "Balancing stop and size...",
    "Calculating capital at risk...",
    "Projecting position units...",
    "Normalizing risk per pip...",
    "Matching stop distance...",
    "Stress-testing the setup...",
    "Finalizing trade size...",
  ],
  command: [
    "Checking command state...",
    "Refreshing command context...",
    "Opening the control panel...",
    "Syncing session controls...",
    "Loading command options...",
    "Preparing command output...",
    "Reviewing active session tools...",
    "Inspecting session settings...",
    "Resolving command view...",
    "Composing command response...",
  ],
  web: [
    "Searching the web...",
    "Scanning live headlines...",
    "Checking macro catalysts...",
    "Pulling fresh market context...",
    "Reviewing breaking developments...",
    "Reading latest news flow...",
    "Cross-checking live sources...",
    "Looking for event risk...",
    "Gathering current web signals...",
    "Searching for fresh context...",
  ],
  chat: [
    "Thinking through the setup...",
    "Propheting through the noise...",
    "Mapping the market picture...",
    "Linking structure and macro...",
    "Reviewing the current context...",
    "Reading the session pulse...",
    "Weighing the strongest angle...",
    "Distilling the cleanest answer...",
    "Connecting the trade narrative...",
    "Sharpening the response...",
  ],
};

const SPINNER_THEME = {
  scan: { frame: ANSI_CYAN, label: ANSI_WHITE },
  bias: { frame: ANSI_GREEN, label: ANSI_WHITE },
  risk: { frame: ANSI_YELLOW, label: ANSI_WHITE },
  command: { frame: ANSI_MAGENTA, label: ANSI_WHITE },
  web: { frame: ANSI_BLUE, label: ANSI_YELLOW },
  chat: { frame: ANSI_CYAN, label: ANSI_WHITE },
};

class UserError extends Error {
  constructor(message, exitCode = 1) {
    super(message);
    this.name = "UserError";
    this.exitCode = exitCode;
  }
}

function normalizeCommand(token) {
  if (!token) {
    return "chat";
  }

  if (["chat", "scan", "bias", "risk"].includes(token)) {
    return token;
  }

  return "chat";
}

function parseFlags(args) {
  const flags = {};
  const positionals = [];

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) {
      positionals.push(arg);
      continue;
    }

    const key = arg.slice(2);
    const next = args[index + 1];
    if (!next || next.startsWith("--")) {
      throw new UserError(`Missing value for --${key}`);
    }

    flags[key] = next;
    index += 1;
  }

  return { flags, positionals };
}

function parseCommand(argv) {
  const filtered = (argv || []).filter(arg => arg !== undefined && arg !== null);
  const first = filtered[0];
  const command = normalizeCommand(first);
  const rest = command === "chat" && first !== "chat" ? filtered : filtered.slice(1);
  const { flags, positionals } = parseFlags(rest);

  if (command === "scan" || command === "bias") {
    return {
      command,
      payload: flags.pair ? { pair: flags.pair } : {},
    };
  }

  if (command === "risk") {
    if (!flags.pair || !flags.sl || !flags.risk) {
      throw new UserError("risk requires --pair, --sl, and --risk");
    }

    const sl = Number(flags.sl);
    const risk = Number(flags.risk);
    if (!Number.isFinite(sl) || !Number.isInteger(sl) || sl <= 0) {
      throw new UserError("--sl must be a positive integer");
    }
    if (!Number.isFinite(risk) || risk <= 0) {
      throw new UserError("--risk must be a positive number");
    }

    return {
      command,
      payload: {
        pair: flags.pair,
        sl,
        risk,
      },
    };
  }

  return {
    command: "chat",
    message: positionals.join(" ").trim(),
  };
}

async function requestJson(fetchImpl, path, payload) {
  const response = await fetchImpl(`${BACKEND_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    const details = typeof data === "string" ? data : JSON.stringify(data);
    throw new UserError(`Backend request failed (${response.status}): ${details}`);
  }

  return data;
}

function printJson(consoleLike, data) {
  consoleLike.log(JSON.stringify(data, null, 2));
}

function writeLine(stream, value) {
  if (stream && typeof stream.write === "function") {
    stream.write(value);
  }
}

function clearCurrentLine(stream, width = 80) {
  writeLine(stream, `\r${" ".repeat(width)}\r`);
}

function parseVersion(version) {
  return String(version || "")
    .split(".")
    .slice(0, 3)
    .map(part => Number.parseInt(part, 10));
}

function isNewerVersion(currentVersion, latestVersion) {
  const current = parseVersion(currentVersion);
  const latest = parseVersion(latestVersion);
  if (current.length !== 3 || latest.length !== 3 || [...current, ...latest].some(Number.isNaN)) {
    return false;
  }

  for (let index = 0; index < 3; index += 1) {
    if (latest[index] > current[index]) {
      return true;
    }
    if (latest[index] < current[index]) {
      return false;
    }
  }

  return false;
}

function formatUpdateNotification(currentVersion, latestVersion) {
  const messageLines = [
    `  Update available: ${currentVersion} → ${latestVersion}`,
    "  Run: npm install -g prophetaf@latest to update",
  ];

  return [
    "╔══════════════════════════════════════════════════════╗",
    ...messageLines.map(line => `║${line.padEnd(UPDATE_BOX_INNER_WIDTH)}║`),
    "╚══════════════════════════════════════════════════════╝",
  ].join("\n");
}

async function readJson(response) {
  if (typeof response.json === "function") {
    return response.json();
  }

  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

function defaultRegistryFetch(url, options = {}) {
  return new Promise((resolve, reject) => {
    const request = https.get(url, { headers: options.headers || {} }, response => {
      const chunks = [];

      response.on("data", chunk => {
        chunks.push(Buffer.from(chunk));
      });
      response.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf8");
        resolve({
          ok: (response.statusCode || 500) >= 200 && (response.statusCode || 500) < 300,
          status: response.statusCode || 500,
          async json() {
            return body ? JSON.parse(body) : null;
          },
          async text() {
            return body;
          },
        });
      });
    });

    request.on("error", reject);
    request.on("socket", socket => {
      if (socket && typeof socket.unref === "function") {
        socket.unref();
      }
    });
    if (typeof request.unref === "function") {
      request.unref();
    }

    if (typeof options.timeoutMs === "number" && options.timeoutMs > 0) {
      request.setTimeout(options.timeoutMs, () => {
        request.destroy(new Error("Registry request timed out"));
      });
    }

    if (options.signal && typeof options.signal.addEventListener === "function") {
      const abortRequest = () => {
        request.destroy(new Error("Registry request aborted"));
      };

      if (options.signal.aborted) {
        abortRequest();
        return;
      }

      options.signal.addEventListener("abort", abortRequest, { once: true });
      request.on("close", () => {
        options.signal.removeEventListener("abort", abortRequest);
      });
    }
  });
}

async function fetchLatestVersion(fetchImpl, options = {}) {
  const packageName = options.packageName || PACKAGE_NAME;
  const timeoutMs = options.timeoutMs || UPDATE_CHECK_TIMEOUT_MS;
  const signal = typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
    ? AbortSignal.timeout(timeoutMs)
    : undefined;
  const response = await fetchImpl(`${NPM_REGISTRY_BASE_URL}/${encodeURIComponent(packageName)}/latest`, {
    headers: { Accept: "application/json" },
    signal,
    timeoutMs,
  });

  if (!response.ok) {
    throw new Error(`Registry request failed (${response.status})`);
  }

  const payload = await readJson(response);
  if (!payload || typeof payload.version !== "string") {
    throw new Error("Registry response did not include a version");
  }

  return payload.version;
}

function startUpdateCheck(fetchImpl, options = {}) {
  let resolved = false;
  let result = null;
  const listeners = new Set();

  const promise = (async () => {
    try {
      const currentVersion = options.currentVersion || CLI_VERSION;
      const latestVersion = await fetchLatestVersion(fetchImpl, options);
      if (!isNewerVersion(currentVersion, latestVersion)) {
        return null;
      }

      return { currentVersion, latestVersion };
    } catch {
      return null;
    }
  })().then(value => {
    resolved = true;
    result = value;
    for (const listener of listeners) {
      listener(value);
    }
    listeners.clear();
    return value;
  });

  return {
    getResult() {
      return resolved ? result : undefined;
    },
    onResult(listener) {
      if (resolved) {
        listener(result);
        return () => {};
      }

      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    promise,
  };
}

function supportsStyle(stream) {
  return Boolean(stream && stream.isTTY);
}

function stylize(text, color, enabled, options = {}) {
  if (!enabled) {
    return text;
  }

  const open = `${options.dim ? ANSI_DIM : ""}${options.bold ? ANSI_BOLD : ""}${color || ""}`;
  return `${open}${text}${ANSI_RESET}`;
}

function visibleLength(text) {
  return String(text || "").replace(ANSI_STRIP_PATTERN, "").length;
}

function shuffleLabels(labels, randomFn = Math.random) {
  const copy = [...labels];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const nextIndex = Math.floor(randomFn() * (index + 1));
    [copy[index], copy[nextIndex]] = [copy[nextIndex], copy[index]];
  }
  return copy;
}

function detectSpinnerMode(path, payload) {
  if (path === "/scan") {
    return "scan";
  }
  if (path === "/bias") {
    return "bias";
  }
  if (path === "/risk") {
    return "risk";
  }

  const message = String(payload && payload.message ? payload.message : "").trim();
  if (message.startsWith("/")) {
    return "command";
  }
  if (WEB_SEARCH_HINT_PATTERN.test(message)) {
    return "web";
  }
  return "chat";
}

function loadingLabelsFor(path, payload, options = {}) {
  const mode = detectSpinnerMode(path, payload);
  const labels = LABEL_SETS[mode];

  if (mode === "chat") {
    return shuffleLabels(labels, options.randomFn);
  }

  return [...labels];
}

function formatSpinnerText(frame, label, theme, enabled) {
  const frameText = stylize(frame, theme.frame, enabled, { bold: true });
  const labelText = stylize(label, theme.label, enabled, { bold: true });
  const trail = stylize("  •  Prophet is working", ANSI_GRAY, enabled, { dim: true });
  return `${frameText} ${labelText}${trail}`;
}

function createSpinner(stream, labels, options = {}) {
  if (!stream || !stream.isTTY || typeof stream.write !== "function") {
    return {
      start() {},
      stop() {},
    };
  }

  const theme = SPINNER_THEME[options.mode] || SPINNER_THEME.chat;
  const styled = supportsStyle(stream);
  let frameIndex = 0;
  let labelIndex = 0;
  let intervalId = null;
  let lastWidth = 0;

  const draw = () => {
    const label = labels[labelIndex % labels.length];
    const frame = SPINNER_FRAMES[frameIndex % SPINNER_FRAMES.length];
    const text = formatSpinnerText(frame, label, theme, styled);
    lastWidth = Math.max(lastWidth, visibleLength(text));
    writeLine(stream, `\r${text}`);
    frameIndex += 1;
    if (frameIndex % SPINNER_FRAMES.length === 0) {
      labelIndex += 1;
    }
  };

  return {
    start() {
      if (intervalId !== null) {
        return;
      }
      draw();
      intervalId = setInterval(draw, 100);
    },
    stop() {
      if (intervalId !== null) {
        clearInterval(intervalId);
        intervalId = null;
      }
      clearCurrentLine(stream, lastWidth);
    },
  };
}

async function requestJsonWithSpinner(fetchImpl, stream, path, payload, options = {}) {
  const mode = detectSpinnerMode(path, payload);
  const spinner = createSpinner(
    stream,
    loadingLabelsFor(path, payload, { randomFn: options.randomFn }),
    { mode },
  );
  spinner.start();
  try {
    return await requestJson(fetchImpl, path, payload);
  } finally {
    spinner.stop();
  }
}

function formatInlineMarkdown(text, styled) {
  let formatted = String(text || "");
  formatted = formatted.replace(/\*\*(.+?)\*\*/g, (_, value) => stylize(value, ANSI_WHITE, styled, { bold: true }));
  formatted = formatted.replace(/`([^`]+)`/g, (_, value) => stylize(value, ANSI_CYAN, styled, { bold: true }));
  formatted = formatted.replace(/\[(.+?)\]\((.+?)\)/g, "$1");
  formatted = formatted.replace(/\*(.+?)\*/g, "$1");
  return formatted;
}

function formatMarkdownMessage(message, options = {}) {
  const styled = Boolean(options.styled);
  const lines = String(message || "").split(/\r?\n/);

  return lines
    .map(line => {
      const trimmed = line.trim();
      if (!trimmed) {
        return "";
      }

      const headingMatch = trimmed.match(/^#{1,6}\s*(.+)$/);
      if (headingMatch) {
        return stylize(formatInlineMarkdown(headingMatch[1], styled), ANSI_YELLOW, styled, { bold: true });
      }

      const bulletMatch = trimmed.match(/^[-*]\s+(.+)$/);
      if (bulletMatch) {
        return `${stylize("•", ANSI_CYAN, styled, { bold: true })} ${formatInlineMarkdown(bulletMatch[1], styled)}`;
      }

      const numberedMatch = trimmed.match(/^(\d+)\.\s+(.+)$/);
      if (numberedMatch) {
        return `${stylize(`${numberedMatch[1]}.`, ANSI_CYAN, styled, { bold: true })} ${formatInlineMarkdown(numberedMatch[2], styled)}`;
      }

      return formatInlineMarkdown(line, styled);
    })
    .join("\n");
}

function renderHelpMenu(consoleLike, commands, options = {}) {
  if (!Array.isArray(commands) || commands.length === 0) {
    return;
  }

  const styled = Boolean(options.styled);
  for (const entry of commands) {
    const [command, description] = Array.isArray(entry) ? entry : [];
    if (!command || !description) {
      continue;
    }
    const commandText = stylize(command.padEnd(13), ANSI_CYAN, styled, { bold: true });
    consoleLike.log(`  ${commandText} ${description}`);
  }
}

function renderModelPicker(consoleLike, metadata, options = {}) {
  if (!metadata || typeof metadata !== "object") {
    return;
  }

  const styled = Boolean(options.styled);
  if (metadata.current) {
    consoleLike.log(`${stylize("Current model:", ANSI_YELLOW, styled, { bold: true })} ${metadata.current}`);
  }
  if (!Array.isArray(metadata.options)) {
    return;
  }

  for (const option of metadata.options) {
    const [name, detail, note] = Array.isArray(option) ? option : [];
    if (!name || !detail) {
      continue;
    }
    consoleLike.log(`  ${stylize(name.padEnd(8), ANSI_CYAN, styled, { bold: true })} ${detail}`);
    if (note) {
      consoleLike.log(`           ${stylize(note, ANSI_GRAY, styled, { dim: true })}`);
    }
  }
}

function renderChatResponse(consoleLike, data, options = {}) {
  const styled = Boolean(options.styled);
  const prefix = stylize("Prophet>", ANSI_YELLOW, styled, { bold: true });
  consoleLike.log(`\n${prefix} ${formatMarkdownMessage(data.message, { styled })}\n`);

  const view = data && data.metadata ? data.metadata.view : null;
  if (view === "help_menu") {
    renderHelpMenu(consoleLike, data.metadata.commands, { styled });
    consoleLike.log("");
    return;
  }
  if (view === "model_picker") {
    renderModelPicker(consoleLike, data.metadata, { styled });
    consoleLike.log("");
  }
}

async function runChat(consoleLike, fetchImpl, overrides, initialMessage) {
  let sessionId = null;
  const output = overrides.stdout || process.stdout;
  const styled = supportsStyle(output);

  const processMessage = async (message) => {
    const trimmed = message.trim();
    if (!trimmed) {
      return true;
    }
    if (trimmed.toLowerCase() === "exit" || trimmed.toLowerCase() === "quit") {
      return false;
    }

    const data = await requestJsonWithSpinner(fetchImpl, output, "/chat", {
      message: trimmed,
      session_id: sessionId,
    }, {
      randomFn: overrides.randomFn,
    });

    sessionId = data.session_id || sessionId;
    renderChatResponse(consoleLike, data, { styled });
    return true;
  };

  if (initialMessage) {
    await processMessage(initialMessage);
    return 0;
  }

  const rl = readline.createInterface({
    input: overrides.stdin || process.stdin,
    output,
  });

  let promptVisible = false;
  let updateNoticeShown = false;
  let pendingUpdateInfo = null;
  const showUpdateNotice = updateInfo => {
    if (!updateInfo || updateNoticeShown) {
      return;
    }

    if (promptVisible && output && output.isTTY) {
      clearCurrentLine(output, 2);
    }

    consoleLike.log(formatUpdateNotification(updateInfo.currentVersion, updateInfo.latestVersion));

    if (promptVisible && output && output.isTTY) {
      writeLine(output, "> ");
    }

    updateNoticeShown = true;
    pendingUpdateInfo = null;
  };

  const updatePromptState = () =>
    promptVisible && (!output || !output.isTTY || (typeof rl.line === "string" && rl.line.length === 0));

  let detachUpdateListener = () => {};
  if (overrides.updateCheck) {
    const readyUpdate = overrides.updateCheck.getResult();
    if (readyUpdate) {
      pendingUpdateInfo = readyUpdate;
    }

    detachUpdateListener = overrides.updateCheck.onResult(updateInfo => {
      if (!updateInfo || updateNoticeShown) {
        return;
      }

      pendingUpdateInfo = updateInfo;
      if (updatePromptState()) {
        showUpdateNotice(updateInfo);
      }
    });
  }

  try {
    consoleLike.log(stylize("Chat session starting... Type /help for commands. Type exit or quit to leave.", ANSI_GRAY, styled, { dim: true }));
    while (true) {
      if (pendingUpdateInfo) {
        showUpdateNotice(pendingUpdateInfo);
      }

      promptVisible = true;
      const answer = await rl.question("> ");
      promptVisible = false;

      const shouldContinue = await processMessage(answer);
      if (!shouldContinue) {
        break;
      }
    }
    return 0;
  } finally {
    detachUpdateListener();
    rl.close();
  }
}

async function runCli(overrides = {}) {
  const consoleLike = overrides.console || global.console;
  const fetchImpl = overrides.fetch || global.fetch;
  if (typeof fetchImpl !== "function") {
    throw new UserError("This runtime does not provide fetch. Use Node.js 18 or newer.");
  }

  consoleLike.log(PROPHET_BANNER);

  const updateCheck = startUpdateCheck(overrides.updateCheckFetch || defaultRegistryFetch, {
    currentVersion: overrides.currentVersion || CLI_VERSION,
    packageName: overrides.packageName || PACKAGE_NAME,
    timeoutMs: overrides.updateCheckTimeoutMs,
  });

  const parsed = parseCommand(overrides.argv || []);
  if (parsed.command === "chat") {
    return runChat(consoleLike, fetchImpl, { ...overrides, updateCheck }, parsed.message);
  }

  const data = await requestJsonWithSpinner(
    fetchImpl,
    overrides.stdout || process.stdout,
    `/${parsed.command}`,
    parsed.payload,
    { randomFn: overrides.randomFn },
  );
  printJson(consoleLike, data);
  return 0;
}

module.exports = {
  BACKEND_BASE_URL,
  NPM_REGISTRY_BASE_URL,
  UserError,
  createSpinner,
  detectSpinnerMode,
  fetchLatestVersion,
  formatMarkdownMessage,
  formatSpinnerText,
  formatUpdateNotification,
  isNewerVersion,
  loadingLabelsFor,
  parseCommand,
  requestJson,
  requestJsonWithSpinner,
  renderChatResponse,
  runCli,
  shuffleLabels,
  startUpdateCheck,
};
