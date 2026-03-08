"use strict";

const readline = require("node:readline/promises");

const PROPHET_BANNER = `
  ██████╗ ██████╗  ██████╗ ██████╗ ██╗  ██╗███████╗████████╗
  ██╔══██╗██╔══██╗██╔═══██╗██╔══██╗██║  ██║██╔════╝╚══██╔══╝
  ██████╔╝██████╔╝██║   ██║██████╔╝███████║█████╗     ██║
  ██╔═══╝ ██╔══██╗██║   ██║██╔═══╝ ██╔══██║██╔══╝     ██║
  ██║     ██║  ██║╚██████╔╝██║     ██║  ██║███████╗   ██║
  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝  ╚═╝╚══════╝   ╚═╝

  Personal AI Trading Assistant  |  v3.1  |  Cloud Edition
`;

const BACKEND_BASE_URL = "https://prophet-wwxjsbvhoa-uc.a.run.app";
const SPINNER_FRAMES = ["-", "\\", "|", "/"];

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

function createSpinner(stream, labels) {
  if (!stream || !stream.isTTY || typeof stream.write !== "function") {
    return {
      start() {},
      stop() {},
    };
  }

  let frameIndex = 0;
  let labelIndex = 0;
  let intervalId = null;
  let lastWidth = 0;

  const draw = () => {
    const label = labels[labelIndex % labels.length];
    const frame = SPINNER_FRAMES[frameIndex % SPINNER_FRAMES.length];
    const text = `${frame} ${label}`;
    lastWidth = Math.max(lastWidth, text.length);
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

function loadingLabelsFor(path, payload) {
  if (path === "/scan") {
    return ["Scanning markets...", "Checking confluence..."];
  }
  if (path === "/bias") {
    return ["Reading market bias...", "Checking structure..."];
  }
  if (path === "/risk") {
    return ["Calculating risk...", "Sizing position..."];
  }

  const message = String(payload && payload.message ? payload.message : "").trim().toLowerCase();
  if (message.startsWith("/")) {
    return ["Thinking...", "Checking command state..."];
  }
  return ["Thinking...", "Propheting..."];
}

async function requestJsonWithSpinner(fetchImpl, stream, path, payload) {
  const spinner = createSpinner(stream, loadingLabelsFor(path, payload));
  spinner.start();
  try {
    return await requestJson(fetchImpl, path, payload);
  } finally {
    spinner.stop();
  }
}

function renderHelpMenu(consoleLike, commands) {
  if (!Array.isArray(commands) || commands.length === 0) {
    return;
  }

  for (const entry of commands) {
    const [command, description] = Array.isArray(entry) ? entry : [];
    if (!command || !description) {
      continue;
    }
    consoleLike.log(`  ${command.padEnd(13)} ${description}`);
  }
}

function renderModelPicker(consoleLike, metadata) {
  if (!metadata || typeof metadata !== "object") {
    return;
  }

  if (metadata.current) {
    consoleLike.log(`Current model: ${metadata.current}`);
  }
  if (!Array.isArray(metadata.options)) {
    return;
  }

  for (const option of metadata.options) {
    const [name, detail, note] = Array.isArray(option) ? option : [];
    if (!name || !detail) {
      continue;
    }
    consoleLike.log(`  ${name.padEnd(8)} ${detail}`);
    if (note) {
      consoleLike.log(`           ${note}`);
    }
  }
}

function renderChatResponse(consoleLike, data) {
  consoleLike.log(`\nProphet> ${data.message}\n`);

  const view = data && data.metadata ? data.metadata.view : null;
  if (view === "help_menu") {
    renderHelpMenu(consoleLike, data.metadata.commands);
    consoleLike.log("");
    return;
  }
  if (view === "model_picker") {
    renderModelPicker(consoleLike, data.metadata);
    consoleLike.log("");
  }
}

async function runChat(consoleLike, fetchImpl, overrides, initialMessage) {
  let sessionId = null;

  const processMessage = async (message) => {
    const trimmed = message.trim();
    if (!trimmed) {
      return true;
    }
    if (trimmed.toLowerCase() === "exit" || trimmed.toLowerCase() === "quit") {
      return false;
    }

    const data = await requestJsonWithSpinner(fetchImpl, overrides.stdout || process.stdout, "/chat", {
      message: trimmed,
      session_id: sessionId,
    });

    sessionId = data.session_id || sessionId;
    renderChatResponse(consoleLike, data);
    return true;
  };

  if (initialMessage) {
    await processMessage(initialMessage);
    return 0;
  }

  const rl = readline.createInterface({
    input: overrides.stdin || process.stdin,
    output: overrides.stdout || process.stdout,
  });

  try {
    consoleLike.log("Chat session starting... Type /help for commands. Type exit or quit to leave.");
    while (true) {
      const answer = await rl.question("> ");
      const shouldContinue = await processMessage(answer);
      if (!shouldContinue) {
        break;
      }
    }
    return 0;
  } finally {
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

  const parsed = parseCommand(overrides.argv || []);
  if (parsed.command === "chat") {
    return runChat(consoleLike, fetchImpl, overrides, parsed.message);
  }

  const data = await requestJsonWithSpinner(
    fetchImpl,
    overrides.stdout || process.stdout,
    `/${parsed.command}`,
    parsed.payload,
  );
  printJson(consoleLike, data);
  return 0;
}

module.exports = {
  BACKEND_BASE_URL,
  UserError,
  createSpinner,
  loadingLabelsFor,
  parseCommand,
  requestJson,
  requestJsonWithSpinner,
  renderChatResponse,
  runCli,
};
