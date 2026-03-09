"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { PassThrough } = require("node:stream");

const {
  BACKEND_BASE_URL,
  NPM_REGISTRY_BASE_URL,
  UserError,
  detectSpinnerMode,
  fetchLatestVersion,
  formatMarkdownMessage,
  formatSpinnerText,
  formatUpdateNotification,
  isNewerVersion,
  loadingLabelsFor,
  parseCommand,
  renderChatResponse,
  runCli,
  shuffleLabels,
  startUpdateCheck,
} = require("../lib/runner");

function createConsole() {
  return {
    messages: [],
    log(message) {
      this.messages.push(message);
    },
  };
}

function createStream({ isTTY = false } = {}) {
  return {
    isTTY,
    writes: [],
    write(chunk) {
      this.writes.push(String(chunk));
      return true;
    },
  };
}

function createFetch(response) {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: response.ok ?? true,
      status: response.status ?? 200,
      async text() {
        return response.body;
      },
    };
  };

  return { calls, fetch };
}

function createJsonResponse(body, extra = {}) {
  return {
    ok: extra.ok ?? true,
    status: extra.status ?? 200,
    async json() {
      return body;
    },
    async text() {
      return JSON.stringify(body);
    },
  };
}

test("parseCommand treats bare text as a chat message", () => {
  assert.deepEqual(parseCommand(["show", "xauusd", "bias"]), {
    command: "chat",
    message: "show xauusd bias",
  });
});

test("parseCommand maps scan flags to the scan payload", () => {
  assert.deepEqual(parseCommand(["scan", "--pair", "XAUUSD"]), {
    command: "scan",
    payload: { pair: "XAUUSD" },
  });
});

test("parseCommand validates the risk command arguments", () => {
  assert.throws(
    () => parseCommand(["risk", "--pair", "XAUUSD", "--risk", "1"]),
    error => {
      assert.ok(error instanceof UserError);
      assert.match(error.message, /risk requires --pair, --sl, and --risk/);
      return true;
    },
  );
});

test("isNewerVersion compares semantic versions safely", () => {
  assert.equal(isNewerVersion("3.2.0", "3.3.0"), true);
  assert.equal(isNewerVersion("3.3.0", "3.2.0"), false);
  assert.equal(isNewerVersion("3.3.0", "3.3.0"), false);
  assert.equal(isNewerVersion("3.2.0", "bad-version"), false);
});

test("formatUpdateNotification matches the boxed update prompt", () => {
  assert.equal(
    formatUpdateNotification("3.2.0", "3.3.0"),
    [
      "╔══════════════════════════════════════════════════════╗",
      "║  Update available: 3.2.0 → 3.3.0                    ║",
      "║  Run: npm install -g prophetaf@latest to update     ║",
      "╚══════════════════════════════════════════════════════╝",
    ].join("\n"),
  );
});

test("fetchLatestVersion reads the npm registry payload", async () => {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({ url, options });
    return createJsonResponse({ version: "3.3.0" });
  };

  const version = await fetchLatestVersion(fetch, {
    packageName: "prophetaf",
    timeoutMs: 250,
  });

  assert.equal(version, "3.3.0");
  assert.equal(calls[0].url, `${NPM_REGISTRY_BASE_URL}/prophetaf/latest`);
});

test("startUpdateCheck swallows registry failures", async () => {
  const updateCheck = startUpdateCheck(async () => {
    throw new Error("registry offline");
  }, {
    currentVersion: "3.2.0",
    packageName: "prophetaf",
  });

  assert.equal(await updateCheck.promise, null);
});

test("detectSpinnerMode routes web-search prompts separately", () => {
  assert.equal(detectSpinnerMode("/chat", { message: "Is Gold good given the news today?" }), "web");
  assert.equal(detectSpinnerMode("/chat", { message: "/model" }), "command");
  assert.equal(detectSpinnerMode("/chat", { message: "Give me a setup summary" }), "chat");
});

test("loadingLabelsFor returns ten randomized chat labels", () => {
  const labels = loadingLabelsFor("/chat", { message: "Give me the outlook" }, {
    randomFn: () => 0,
  });

  assert.equal(labels.length, 10);
  assert.ok(labels.every(label => typeof label === "string" && label.length > 0));
  assert.equal(new Set(labels).size, 10);
});

test("loadingLabelsFor returns dedicated web-search labels", () => {
  const labels = loadingLabelsFor("/chat", { message: "What is the latest Gold news today?" });

  assert.equal(labels.length, 10);
  assert.ok(labels.includes("Searching the web..."));
  assert.ok(labels.includes("Scanning live headlines..."));
});

test("shuffleLabels preserves all labels", () => {
  const labels = ["a", "b", "c", "d"];
  const shuffled = shuffleLabels(labels, () => 0.25);

  assert.deepEqual([...shuffled].sort(), [...labels].sort());
});

test("formatSpinnerText adds design accents for tty output", () => {
  const text = formatSpinnerText("◐", "Searching the web...", { frame: "\u001b[34m", label: "\u001b[33m" }, true);

  assert.match(text, /\u001b\[34m/);
  assert.match(text, /Searching the web/);
  assert.match(text, /Prophet is working/);
});

test("formatMarkdownMessage strips raw markdown markers into readable terminal text", () => {
  const formatted = formatMarkdownMessage(
    "### **Market Context**\n* **Bias:** Bullish\n* **News:** Check headlines",
    { styled: false },
  );

  assert.equal(
    formatted,
    ["Market Context", "• Bias: Bullish", "• News: Check headlines"].join("\n"),
  );
  assert.doesNotMatch(formatted, /\*\*|###/);
});

test("runCli sends one-off chat messages to the live backend URL", async () => {
  const fakeConsole = createConsole();
  const stream = createStream();
  const { calls, fetch } = createFetch({
    body: JSON.stringify({ message: "Hello from Prophet", session_id: "abc123" }),
  });

  const exitCode = await runCli({
    argv: ["hello there"],
    console: fakeConsole,
    fetch,
    stdin: process.stdin,
    stdout: stream,
  });

  assert.equal(exitCode, 0);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `${BACKEND_BASE_URL}/chat`);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    message: "hello there",
    session_id: null,
  });
  assert.match(fakeConsole.messages[1], /Prophet> Hello from Prophet/);
});

test("runCli prints JSON for scan responses", async () => {
  const fakeConsole = createConsole();
  const stream = createStream();
  const { calls, fetch } = createFetch({
    body: JSON.stringify([{ pair: "XAUUSD", bias: "bullish" }]),
  });

  const exitCode = await runCli({
    argv: ["scan", "--pair", "XAUUSD"],
    console: fakeConsole,
    fetch,
    stdout: stream,
  });

  assert.equal(exitCode, 0);
  assert.equal(calls[0].url, `${BACKEND_BASE_URL}/scan`);
  assert.deepEqual(JSON.parse(calls[0].options.body), { pair: "XAUUSD" });
  assert.match(fakeConsole.messages[1], /"pair": "XAUUSD"/);
});

test("runCli prints JSON for risk responses", async () => {
  const fakeConsole = createConsole();
  const stream = createStream();
  const { calls, fetch } = createFetch({
    body: JSON.stringify({ pair: "XAUUSD", units: 0.67 }),
  });

  const exitCode = await runCli({
    argv: ["risk", "--pair", "XAUUSD", "--sl", "15", "--risk", "1"],
    console: fakeConsole,
    fetch,
    stdout: stream,
  });

  assert.equal(exitCode, 0);
  assert.equal(calls[0].url, `${BACKEND_BASE_URL}/risk`);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    pair: "XAUUSD",
    sl: 15,
    risk: 1,
  });
  assert.match(fakeConsole.messages[1], /"units": 0.67/);
});

test("runCli surfaces backend failures clearly", async () => {
  const { fetch } = createFetch({
    ok: false,
    status: 500,
    body: "Internal Server Error",
  });

  await assert.rejects(
    () =>
      runCli({
        argv: ["bias", "--pair", "XAUUSD"],
        console: createConsole(),
        fetch,
        stdout: createStream(),
      }),
    error => {
      assert.ok(error instanceof UserError);
      assert.match(error.message, /Backend request failed \(500\): Internal Server Error/);
      return true;
    },
  );
});

test("runCli does not wait for the registry check before sending a one-off chat message", async () => {
  let resolveRegistry;
  const updateCheckFetch = () =>
    new Promise(resolve => {
      resolveRegistry = resolve;
    });
  const { calls, fetch } = createFetch({
    body: JSON.stringify({ message: "Hello from Prophet", session_id: "abc123" }),
  });

  const exitCode = await runCli({
    argv: ["hello there"],
    console: createConsole(),
    fetch,
    updateCheckFetch,
    stdout: createStream(),
  });

  assert.equal(exitCode, 0);
  assert.equal(calls.length, 1);
  resolveRegistry(createJsonResponse({ version: "3.3.0" }));
});

test("runCli shows the update box during interactive chat startup when a newer version is found", async () => {
  const fakeConsole = createConsole();
  const stdout = new PassThrough();
  stdout.isTTY = true;
  stdout.writes = [];
  const originalWrite = stdout.write.bind(stdout);
  stdout.write = chunk => {
    stdout.writes.push(String(chunk));
    return originalWrite(chunk);
  };

  const stdin = new PassThrough();
  const updateCheckFetch = async () => createJsonResponse({ version: "3.4.0" });

  const runPromise = runCli({
    argv: [],
    console: fakeConsole,
    fetch: async () => {
      throw new Error("backend should not be called");
    },
    updateCheckFetch,
    stdin,
    stdout,
    currentVersion: "3.3.0",
  });

  await new Promise(resolve => setImmediate(resolve));
  stdin.end("quit\n");

  const exitCode = await runPromise;

  assert.equal(exitCode, 0);
  assert.match(fakeConsole.messages[0], /Personal AI Trading Assistant  \|  v3\.3\.0  \|  Cloud Edition/);
  assert.equal(
    fakeConsole.messages[2],
    [
      "╔══════════════════════════════════════════════════════╗",
      "║  Update available: 3.3.0 → 3.4.0                    ║",
      "║  Run: npm install -g prophetaf@latest to update     ║",
      "╚══════════════════════════════════════════════════════╝",
    ].join("\n"),
  );
});

test("renderChatResponse prints markdown without raw markers", () => {
  const fakeConsole = createConsole();

  renderChatResponse(fakeConsole, {
    message: "### **Market Context**\n* **Bias:** Bullish\n* **Session:** Asia open",
    metadata: {},
  }, { styled: false });

  assert.match(fakeConsole.messages[0], /Market Context/);
  assert.match(fakeConsole.messages[0], /• Bias: Bullish/);
  assert.doesNotMatch(fakeConsole.messages[0], /\*\*|###/);
});

test("renderChatResponse prints the help command list", () => {
  const fakeConsole = createConsole();

  renderChatResponse(fakeConsole, {
    message: "Open the command palette below.",
    metadata: {
      view: "help_menu",
      commands: [
        ["/help", "Show the command palette"],
        ["/model", "Inspect or switch the active session model"],
      ],
    },
  }, { styled: false });

  assert.match(fakeConsole.messages[0], /Open the command palette below/);
  assert.equal(fakeConsole.messages[1], "  /help         Show the command palette");
  assert.equal(fakeConsole.messages[2], "  /model        Inspect or switch the active session model");
});

test("renderChatResponse prints model picker details", () => {
  const fakeConsole = createConsole();

  renderChatResponse(fakeConsole, {
    message: "Choose the active model for this session.",
    metadata: {
      view: "model_picker",
      current: "auto",
      options: [
        ["auto", "Gemini -> OpenAI fallback", "Best default for most sessions"],
        ["gemini", "gemini-3-flash-preview", "Fast market reasoning with Gemini only"],
      ],
    },
  }, { styled: false });

  assert.match(fakeConsole.messages[0], /Choose the active model for this session/);
  assert.equal(fakeConsole.messages[1], "Current model: auto");
  assert.equal(fakeConsole.messages[2], "  auto     Gemini -> OpenAI fallback");
  assert.equal(fakeConsole.messages[3], "           Best default for most sessions");
});

test("runCli drives the styled spinner for tty chat requests", async () => {
  const fakeConsole = createConsole();
  const stream = createStream({ isTTY: true });
  const { fetch } = createFetch({
    body: JSON.stringify({ message: "Hello from Prophet", session_id: "abc123" }),
  });

  await runCli({
    argv: ["What is the latest Gold news today?"],
    console: fakeConsole,
    fetch,
    stdin: process.stdin,
    stdout: stream,
    randomFn: () => 0,
  });

  assert.ok(stream.writes.some(chunk => chunk.includes("Searching the web...")));
  assert.ok(stream.writes.some(chunk => chunk.includes("\u001b[")));
  assert.ok(stream.writes.some(chunk => /\r\s+\r/.test(chunk)));
});
