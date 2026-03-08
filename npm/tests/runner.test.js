"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  BACKEND_BASE_URL,
  UserError,
  loadingLabelsFor,
  parseCommand,
  renderChatResponse,
  runCli,
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
      this.writes.push(chunk);
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
  });

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
  });

  assert.match(fakeConsole.messages[0], /Choose the active model for this session/);
  assert.equal(fakeConsole.messages[1], "Current model: auto");
  assert.equal(fakeConsole.messages[2], "  auto     Gemini -> OpenAI fallback");
  assert.equal(fakeConsole.messages[3], "           Best default for most sessions");
});

test("loadingLabelsFor chooses command-aware spinner text", () => {
  assert.deepEqual(loadingLabelsFor("/scan", {}), ["Scanning markets...", "Checking confluence..."]);
  assert.deepEqual(loadingLabelsFor("/chat", { message: "/help" }), ["Thinking...", "Checking command state..."]);
  assert.deepEqual(loadingLabelsFor("/chat", { message: "fed this week?" }), ["Thinking...", "Propheting..."]);
});

test("runCli drives and clears the spinner for tty chat requests", async () => {
  const fakeConsole = createConsole();
  const stream = createStream({ isTTY: true });
  const { fetch } = createFetch({
    body: JSON.stringify({ message: "Hello from Prophet", session_id: "abc123" }),
  });

  await runCli({
    argv: ["hello there"],
    console: fakeConsole,
    fetch,
    stdin: process.stdin,
    stdout: stream,
  });

  assert.ok(stream.writes.some(chunk => chunk.includes("Thinking...")));
  assert.ok(stream.writes.some(chunk => /\r\s+\r/.test(chunk)));
});
