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
const EXPLICIT_WEB_HINT_PATTERN = /\b(headline|headlines|breaking|news|live news|latest news|search the web|web search|look up|look this up|search online)\b/i;
const EVENT_RISK_PATTERN = /\b(cpi|nfp|fomc|fed|ecb|boe|boj|tariff|geopolitical|rate decision|inflation print)\b/i;
const RECENCY_PATTERN = /\b(today|latest|current|live|now|recent)\b/i;

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

  if (["chat", "scan", "bias", "risk", "resume"].includes(token)) {
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

  if (command === "resume") {
    return {
      command,
    };
  }

  return {
    command: "chat",
    message: positionals.join(" ").trim(),
  };
}

function responseHeaderValue(response, name) {
  if (!response || !response.headers) {
    return "";
  }
  if (typeof response.headers.get === "function") {
    return response.headers.get(name) || "";
  }
  const direct = response.headers[name] || response.headers[name.toLowerCase()];
  return typeof direct === "string" ? direct : "";
}

async function requestJson(fetchImpl, path, payload, options = {}) {
  const method = options.method || "POST";
  const headers = { ...(options.headers || {}) };
  const request = {
    method,
    headers,
  };
  if (payload !== undefined && payload !== null) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
    request.body = JSON.stringify(payload);
  }

  const response = await fetchImpl(`${BACKEND_BASE_URL}${path}`, request);

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

async function requestGetJson(fetchImpl, path, query = null) {
  const suffix = query ? `?${new URLSearchParams(query).toString()}` : "";
  const response = await fetchImpl(`${BACKEND_BASE_URL}${path}${suffix}`, {
    method: "GET",
    headers: { Accept: "application/json" },
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

function shouldUseWebSpinner(message) {
  const value = String(message || "").trim();
  if (!value) {
    return false;
  }
  if (EXPLICIT_WEB_HINT_PATTERN.test(value)) {
    return true;
  }
  return EVENT_RISK_PATTERN.test(value) && RECENCY_PATTERN.test(value);
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
  if (shouldUseWebSpinner(message)) {
    return "web";
  }
  return "chat";
}

function loadingLabelsFor(path, payload, options = {}) {
  const mode = detectSpinnerMode(path, payload);
  return shuffleLabels(LABEL_SETS[mode], options.randomFn);
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
      setLabel() {},
    };
  }

  const theme = SPINNER_THEME[options.mode] || SPINNER_THEME.chat;
  const styled = supportsStyle(stream);
  let frameIndex = 0;
  let labelIndex = 0;
  let intervalId = null;
  let lastWidth = 0;
  let overrideLabel = null;

  const draw = () => {
    const label = overrideLabel || labels[labelIndex % labels.length];
    const frame = SPINNER_FRAMES[frameIndex % SPINNER_FRAMES.length];
    const text = formatSpinnerText(frame, label, theme, styled);
    lastWidth = Math.max(lastWidth, visibleLength(text));
    writeLine(stream, `\r${text}`);
    frameIndex += 1;
    if (!overrideLabel && frameIndex % SPINNER_FRAMES.length === 0) {
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
    setLabel(label) {
      overrideLabel = label ? String(label) : null;
      if (intervalId !== null) {
        draw();
      }
    },
  };
}

function supportsInteractive(input, output) {
  return Boolean(input && input.isTTY && output && output.isTTY);
}

function formatCalendarPayload(payload) {
  const events = Array.isArray(payload && payload.events) ? payload.events : [];
  const warnings = Array.isArray(payload && payload.warnings) ? payload.warnings : [];
  if (events.length === 0 && warnings.length === 0) {
    return "No calendar events returned for that view.";
  }

  const lines = events.map(event =>
    `${event.date} ${event.time_utc} UTC | ${event.currency} | ${event.impact} | ${event.event_name}`,
  );
  for (const warning of warnings) {
    lines.push(`Warning: ${warning.message}`);
  }
  return lines.join("\n");
}

async function loadPrompts(overrides) {
  if (overrides.prompts) {
    return overrides.prompts;
  }
  return import("@inquirer/prompts");
}

function isPromptCancelError(error) {
  if (!error || typeof error !== "object") {
    return false;
  }
  const name = typeof error.name === "string" ? error.name : "";
  const message = typeof error.message === "string" ? error.message : "";
  return (
    name === "ExitPromptError"
    || name === "AbortPromptError"
    || message.includes("User force closed")
    || message.includes("Prompt was canceled")
  );
}

function parseSseEvents(buffer, onEvent) {
  let remaining = buffer;
  while (true) {
    const boundary = remaining.indexOf("\n\n");
    if (boundary === -1) {
      break;
    }
    const rawEvent = remaining.slice(0, boundary);
    remaining = remaining.slice(boundary + 2);
    const lines = rawEvent.split(/\r?\n/);
    let eventName = "message";
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (dataLines.length === 0) {
      continue;
    }
    let payload = dataLines.join("\n");
    try {
      payload = JSON.parse(payload);
    } catch {
      // Keep raw payload when it is not JSON.
    }
    onEvent(eventName, payload);
  }
  return remaining;
}

function stripMarkdownSyntax(text) {
  return String(text || "")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map(line => line
      .replace(/^(\s*)#{1,6}\s*/g, "$1")
      .replace(/^(\s*)[-*]\s+/g, "$1• ")
      .replace(/\[(.+?)\]\((.+?)\)/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*(.+?)\*\*/g, "$1")
      .replace(/__(.+?)__/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/_([^_]+)_/g, "$1"))
    .join("\n");
}

async function requestChat(fetchImpl, stream, payload, options = {}) {
  const mode = detectSpinnerMode("/chat", payload);
  const spinner = createSpinner(
    stream,
    loadingLabelsFor("/chat", payload, { randomFn: options.randomFn }),
    { mode },
  );
  spinner.start();

  const response = await fetchImpl(`${BACKEND_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream, application/json",
    },
    body: JSON.stringify({ ...payload, stream: true }),
  });

  if (!response.ok) {
    spinner.stop();
    const text = await response.text();
    throw new UserError(`Backend request failed (${response.status}): ${text}`);
  }

  const contentType = responseHeaderValue(response, "content-type");
  const canStream = contentType.includes("text/event-stream")
    && response.body
    && typeof response.body.getReader === "function";
  if (!canStream) {
    spinner.stop();
    const text = await response.text();
    let data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { message: text };
      }
    }
    return data;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawChunk = false;
  let donePayload = null;
  let streamError = null;
  let renderedPrefix = false;
  let sawReasoning = false;
  let spinnerTimer = null;
  let streamedRawText = "";
  let renderedPlainText = "";

  const clearSpinnerTimer = () => {
    if (spinnerTimer !== null) {
      clearTimeout(spinnerTimer);
      spinnerTimer = null;
    }
  };

  const stopSpinner = ({ markChunk = false } = {}) => {
    clearSpinnerTimer();
    if (markChunk) {
      sawChunk = true;
    }
    spinner.stop();
  };

  const scheduleSpinner = () => {
    if (sawChunk) {
      return;
    }
    clearSpinnerTimer();
    spinnerTimer = setTimeout(() => {
      spinner.start();
      spinnerTimer = null;
    }, 180);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = parseSseEvents(buffer, (eventName, eventPayload) => {
      if (eventName === "message" && eventPayload && typeof eventPayload.delta === "string") {
        stopSpinner({ markChunk: true });
        if (!renderedPrefix) {
          if (sawReasoning) {
            writeLine(stream, "\n");
          }
          renderStreamedPrefix(stream, supportsStyle(stream));
          renderedPrefix = true;
        }
        streamedRawText += eventPayload.delta;
        const formatted = stripMarkdownSyntax(streamedRawText);
        const nextText = formatted.slice(renderedPlainText.length);
        renderedPlainText = formatted;
        if (nextText) {
          writeLine(stream, nextText);
        }
      } else if (!sawChunk && eventName === "step" && eventPayload && typeof eventPayload.message === "string") {
        stopSpinner();
        spinner.setLabel(eventPayload.message);
        scheduleSpinner();
      } else if (!sawChunk && eventName === "reasoning" && eventPayload && typeof eventPayload.message === "string") {
        stopSpinner();
        sawReasoning = true;
        renderReasoningLine(stream, eventPayload.message, supportsStyle(stream));
        scheduleSpinner();
      } else if (eventName === "done") {
        stopSpinner();
        donePayload = eventPayload;
      } else if (eventName === "error") {
        stopSpinner();
        streamError = eventPayload;
      }
    });
    if (streamError) {
      break;
    }
  }

  clearSpinnerTimer();
  spinner.stop();
  if (streamError) {
    if (typeof reader.cancel === "function") {
      await reader.cancel();
    }
    throw new UserError(streamError.message || "Streaming chat request failed.");
  }
  if (sawChunk) {
    writeLine(stream, "\n");
  }
  return { ...(donePayload || { message: "" }), __streamed: sawChunk };
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

function extractInlineSegments(text) {
  const segments = [];
  let value = String(text || "");
  value = value.replace(/\*\*(.+?)\*\*/g, (_, content) => {
    const token = `\u0000${segments.length}\u0000`;
    segments.push({ token, text: content, style: "bold" });
    return token;
  });
  value = value.replace(/`([^`]+)`/g, (_, content) => {
    const token = `\u0000${segments.length}\u0000`;
    segments.push({ token, text: content, style: "code" });
    return token;
  });
  value = value.replace(/\[(.+?)\]\((.+?)\)/g, "$1");
  value = value.replace(/\*([^*]+)\*/g, "$1");
  return { value, segments };
}

function restoreInlineSegments(text, segments, styled) {
  let value = text;
  for (const segment of segments) {
    const rendered = segment.style === "code"
      ? stylize(segment.text, ANSI_CYAN, styled, { bold: true })
      : stylize(segment.text, ANSI_WHITE, styled, { bold: true });
    value = value.replace(segment.token, rendered);
  }
  return value;
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

      const { value, segments } = extractInlineSegments(trimmed);

      const headingMatch = value.match(/^#{1,6}\s*(.+)$/);
      if (headingMatch) {
        return stylize(restoreInlineSegments(headingMatch[1], segments, styled), ANSI_YELLOW, styled, { bold: true });
      }

      const bulletMatch = value.match(/^[-*]\s+(.+)$/);
      if (bulletMatch) {
        return `${stylize("•", ANSI_CYAN, styled, { bold: true })} ${restoreInlineSegments(bulletMatch[1], segments, styled)}`;
      }

      const numberedMatch = value.match(/^(\d+)\.\s+(.+)$/);
      if (numberedMatch) {
        return `${stylize(`${numberedMatch[1]}.`, ANSI_CYAN, styled, { bold: true })} ${restoreInlineSegments(numberedMatch[2], segments, styled)}`;
      }

      return restoreInlineSegments(value, segments, styled);
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
  consoleLike.log(`\n${prefix} ${stripMarkdownSyntax(data.message)}\n`);

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

function renderStreamedPrefix(output, styled) {
  const prefix = stylize("Prophet>", ANSI_YELLOW, styled, { bold: true });
  writeLine(output, `\n${prefix} `);
}

function renderReasoningLine(output, message, styled) {
  const text = String(message || "").trim();
  if (!text) {
    return;
  }
  const bullet = stylize("◆", ANSI_GRAY, styled, { bold: true });
  const body = stylize(text, ANSI_GRAY, styled, { dim: true });
  writeLine(output, `${bullet} ${body}\n`);
}

function renderPostStreamResponse(consoleLike, data, options = {}) {
  const view = data && data.metadata ? data.metadata.view : null;
  const styled = Boolean(options.styled);
  if (view === "help_menu") {
    renderHelpMenu(consoleLike, data.metadata.commands, { styled });
    consoleLike.log("");
  }
  if (view === "model_picker") {
    renderModelPicker(consoleLike, data.metadata, { styled });
    consoleLike.log("");
  }
}

async function runChat(consoleLike, fetchImpl, overrides, initialMessage) {
  let sessionId = null;
  let history = [];
  const output = overrides.stdout || process.stdout;
  const input = overrides.stdin || process.stdin;
  const styled = supportsStyle(output);
  let activeRl = null;

  const closePromptInterface = () => {
    if (activeRl) {
      activeRl.close();
      activeRl = null;
    }
  };

  const recordTurn = (userMessage, response) => {
    history.push({ role: "user", content: userMessage, metadata: {} });
    history.push({
      role: "assistant",
      content: response && typeof response.message === "string" ? response.message : "",
      metadata: response && response.metadata ? response.metadata : {},
    });
  };

  const buildPayload = message => ({
    message,
    session_id: sessionId,
    history: [...history, { role: "user", content: message, metadata: {} }],
  });

  const resumeSession = async sessionRef => {
    const payload = await requestJson(fetchImpl, `/sessions/resume/${encodeURIComponent(sessionRef)}`, null, {
      method: "POST",
    });
    sessionId = payload.id || sessionRef;
    history = Array.isArray(payload.messages) ? payload.messages.map(item => ({
      role: item.role,
      content: item.content,
      metadata: item.metadata || {},
    })) : [];
    if (payload.recap) {
      renderChatResponse(consoleLike, { message: payload.recap, metadata: {} }, { styled });
    }
    return payload;
  };

  const resumeLatestSession = async () => {
    const sessions = await requestGetJson(fetchImpl, "/sessions");
    if (!Array.isArray(sessions) || sessions.length === 0) {
      consoleLike.log(stylize("No saved sessions found. Starting a new chat.", ANSI_GRAY, styled, { dim: true }));
      return false;
    }
    await resumeSession(sessions[0].id);
    return true;
  };

  const sendChatMessage = async message => {
    const trimmed = message.trim();
    if (!trimmed) {
      return true;
    }
    if (trimmed.toLowerCase() === "exit" || trimmed.toLowerCase() === "quit") {
      return false;
    }

    const data = await requestChat(fetchImpl, output, buildPayload(trimmed), {
      randomFn: overrides.randomFn,
    });

    sessionId = data.session_id || sessionId;
    recordTurn(trimmed, data);
    if (!data.__streamed) {
      renderChatResponse(consoleLike, data, { styled });
    } else {
      renderPostStreamResponse(consoleLike, data, { styled });
    }
    return !(data && data.should_exit);
  };

  const fetchCommandPreview = async command => {
    const payload = await requestJson(fetchImpl, "/chat", {
      ...buildPayload(command),
      stream: false,
    });
    sessionId = payload.session_id || sessionId;
    return payload;
  };

  const handleCalendarSelector = async () => {
    try {
      const prompts = await loadPrompts(overrides);
      const choices = [
        { name: "Today", value: { view: "today" } },
        { name: "This week", value: { view: "week" } },
      ];
      const selection = await prompts.select({ message: "Calendar view", choices });
      const payload = await requestGetJson(fetchImpl, "/calendar", { view: selection.view });
      const message = formatCalendarPayload(payload);
      const response = { message, metadata: { ...payload, view: "calendar_picker" } };
      history.push({ role: "user", content: "/calendar", metadata: {} });
      history.push({ role: "assistant", content: message, metadata: response.metadata });
      renderChatResponse(consoleLike, response, { styled });
      return true;
    } catch (error) {
      if (isPromptCancelError(error)) {
        return true;
      }
      throw error;
    }
  };

  const handleInteractiveSlashCommand = async message => {
    if (!supportsInteractive(input, output)) {
      return null;
    }
    const trimmed = message.trim();
    if (!["/model", "/pairs", "/sessions", "/calendar"].includes(trimmed)) {
      return null;
    }

    if (trimmed === "/sessions") {
      try {
        const prompts = await loadPrompts(overrides);
        const sessions = await requestGetJson(fetchImpl, "/sessions");
        if (!Array.isArray(sessions) || sessions.length === 0) {
          renderChatResponse(consoleLike, { message: "No saved sessions yet.", metadata: {} }, { styled });
          return true;
        }
        const selected = await prompts.select({
          message: "Select a session to resume",
          choices: sessions.map((item, index) => ({
            name: `${index + 1}. ${item.summary || "No summary yet."}`,
            value: item.id,
          })),
        });
        await resumeSession(selected);
      } catch (error) {
        if (!isPromptCancelError(error)) {
          throw error;
        }
      }
      return true;
    }

    if (trimmed === "/calendar") {
      return handleCalendarSelector();
    }

    if (trimmed === "/model") {
      try {
        const preview = await fetchCommandPreview("/model");
        const prompts = await loadPrompts(overrides);
        const selected = await prompts.select({
          message: "Select AI model",
          choices: (preview.metadata.options || []).map(option => ({
            name: option[0] === preview.metadata.current ? `${option[0]} (current)` : option[0],
            value: option[0],
          })),
        });
        const response = await requestJson(fetchImpl, "/chat", {
          ...buildPayload(`/model ${selected}`),
          stream: false,
        });
        sessionId = response.session_id || sessionId;
        recordTurn(`/model ${selected}`, response);
        renderChatResponse(consoleLike, response, { styled });
      } catch (error) {
        if (!isPromptCancelError(error)) {
          throw error;
        }
      }
      return true;
    }

    if (trimmed === "/pairs") {
      try {
        const preview = await fetchCommandPreview("/pairs");
        const prompts = await loadPrompts(overrides);
        const action = await prompts.select({
          message: "Watchlist action",
          choices: (preview.metadata.actions || []).map(item => ({ name: item, value: item })),
        });
        if (action === "View current pairs") {
          renderChatResponse(consoleLike, preview, { styled });
          return true;
        }
        if (action === "Add a pair") {
          const pair = await prompts.input({ message: "Which pair would you like to add?" });
          if (!pair || !pair.trim()) {
            return true;
          }
          const response = await requestJson(fetchImpl, "/chat", {
            ...buildPayload(`/pairs add ${pair}`),
            stream: false,
          });
          sessionId = response.session_id || sessionId;
          recordTurn(`/pairs add ${pair}`, response);
          renderChatResponse(consoleLike, response, { styled });
          return true;
        }
        const pairChoices = (preview.metadata.pairs || []).map(item => ({ name: item, value: item }));
        const pair = await prompts.select({ message: "Select a pair to remove", choices: pairChoices });
        const response = await requestJson(fetchImpl, "/chat", {
          ...buildPayload(`/pairs remove ${pair}`),
          stream: false,
        });
        sessionId = response.session_id || sessionId;
        recordTurn(`/pairs remove ${pair}`, response);
        renderChatResponse(consoleLike, response, { styled });
      } catch (error) {
        if (!isPromptCancelError(error)) {
          throw error;
        }
        return true;
      }
      return true;
    }

    return null;
  };

  if (overrides.resumeLatest) {
    await resumeLatestSession();
  }

  if (initialMessage) {
    await sendChatMessage(initialMessage);
    return 0;
  }

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
    promptVisible && (!output || !output.isTTY || (activeRl && typeof activeRl.line === "string" && activeRl.line.length === 0));

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

      activeRl = readline.createInterface({
        input,
        output,
      });
      promptVisible = true;
      let answer;
      try {
        answer = await activeRl.question("> ");
      } finally {
        promptVisible = false;
        closePromptInterface();
      }

      const interactiveHandled = await handleInteractiveSlashCommand(answer);
      if (interactiveHandled !== null) {
        if (!interactiveHandled) {
          break;
        }
        continue;
      }

      const shouldContinue = await sendChatMessage(answer);
      if (!shouldContinue) {
        break;
      }
    }
    return 0;
  } finally {
    detachUpdateListener();
    closePromptInterface();
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
  if (parsed.command === "resume") {
    return runChat(consoleLike, fetchImpl, { ...overrides, updateCheck, resumeLatest: true }, null);
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
  renderReasoningLine,
  runCli,
  shuffleLabels,
  startUpdateCheck,
};
