"use strict";

const configStore = require("./config");

const INTRO_BLOCK = [
  "──────────────────────────────────────────────────",
  "  Welcome to Prophet.",
  "  ",
  "  Let's set up your trading profile.",
  "  This takes about 60 seconds and only happens once.",
  "──────────────────────────────────────────────────",
].join("\n");

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

function welcomeBlock(displayName) {
  return [
    "──────────────────────────────────────────",
    `  Welcome, ${displayName}.`,
    "  Your Prophet profile is ready.",
    "  Type anything to begin your session.",
    "──────────────────────────────────────────",
  ].join("\n");
}

async function loadPrompts(overrides = {}) {
  if (overrides.prompts) {
    return overrides.prompts;
  }
  return import("@inquirer/prompts");
}

async function runOnboarding(options = {}) {
  const consoleLike = options.console || global.console;
  const fetchImpl = options.fetch || global.fetch;
  const config = options.config || configStore;
  const prompts = await loadPrompts(options);
  const promptContext = {
    input: options.stdin || process.stdin,
    output: options.stdout || process.stdout,
    clearPromptOnDone: true,
  };

  consoleLike.log(INTRO_BLOCK);

  try {
    const display_name = await prompts.input({
      message: "What should Prophet call you?",
      validate(value) {
        const trimmed = String(value || "").trim();
        if (trimmed.length < 2) {
          return "Enter at least 2 characters.";
        }
        return true;
      },
    }, promptContext);

    const experience_level = await prompts.select({
      message: "How would you describe your trading experience?",
      choices: [
        { name: "Just getting started", value: "beginner" },
        { name: "Some experience", value: "intermediate" },
        { name: "Experienced trader", value: "experienced" },
        { name: "Professional / Full-time", value: "professional" },
      ],
    }, promptContext);

    const watchlist = await prompts.checkbox({
      message: "Which markets do you trade? (select all that apply)",
      choices: [
        { name: "XAUUSD (Gold)", value: "XAUUSD" },
        { name: "EURUSD", value: "EURUSD" },
        { name: "GBPUSD", value: "GBPUSD" },
        { name: "USDJPY", value: "USDJPY" },
        { name: "USDCHF", value: "USDCHF" },
      ],
      validate(value) {
        return Array.isArray(value) && value.length > 0 ? true : "Select at least one market.";
      },
    }, promptContext);

    const balanceText = await prompts.input({
      message: "What is your trading account balance? (USD, numbers only)",
      default: "10000",
      validate(value) {
        const amount = Number(value);
        return Number.isFinite(amount) && amount > 0 ? true : "Enter a number greater than 0.";
      },
    }, promptContext);

    const risk_pct = await prompts.select({
      message: "What is your maximum risk per trade?",
      choices: [
        { name: "0.5% per trade (conservative)", value: 0.5 },
        { name: "1% per trade (standard)", value: 1.0 },
      ],
    }, promptContext);

    const min_rr = await prompts.select({
      message: "What is your minimum acceptable risk-reward ratio?",
      choices: [
        { name: "1:2 minimum", value: "1:2" },
        { name: "1:3 minimum", value: "1:3" },
      ],
    }, promptContext);

    const sessions = await prompts.checkbox({
      message: "Which sessions do you trade?",
      choices: [
        { name: "London session", value: "London" },
        { name: "New York session", value: "New York" },
        { name: "London-NY overlap", value: "London-NY Overlap" },
      ],
      validate(value) {
        return Array.isArray(value) && value.length > 0 ? true : "Select at least one session.";
      },
    }, promptContext);

    const confirmed = await prompts.confirm({
      message: "Ready to create your Prophet profile?",
      default: true,
    }, promptContext);

    if (!confirmed) {
      consoleLike.log("No problem. Run prophetaf again when ready.");
      return { status: "cancelled" };
    }

    consoleLike.log("  Setting up your profile...");

    const payload = {
      display_name: String(display_name).trim(),
      experience_level,
      watchlist,
      account_balance: Number(balanceText),
      risk_pct,
      min_rr,
      sessions,
    };

    const response = await fetchImpl(`${options.backendBaseUrl || "https://prophet-wwxjsbvhoa-uc.a.run.app"}/api/v1/onboard`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });

    const raw = await response.text();
    const data = raw ? JSON.parse(raw) : {};
    if (!response.ok) {
      throw new Error(data.detail || raw || `Onboarding failed (${response.status})`);
    }

    const saved = config.writeConfig({
      device_token: data.device_token,
      display_name: data.display_name,
      created_at: new Date().toISOString(),
      onboarded: true,
    });
    if (!saved) {
      throw new Error("Could not save ~/.prophet/config.json");
    }

    consoleLike.log(welcomeBlock(data.display_name));
    if (data.prophet_md_preview) {
      consoleLike.log(data.prophet_md_preview);
    }
    return { status: "completed", profile: data };
  } catch (error) {
    if (isPromptCancelError(error)) {
      consoleLike.log("No problem. Run prophetaf again when ready.");
      return { status: "cancelled" };
    }
    const message = error instanceof Error ? error.message : String(error);
    consoleLike.log(`Prophet setup failed: ${message}`);
    consoleLike.log("Please try running prophetaf again.");
    return { status: "failed", error };
  }
}

module.exports = {
  INTRO_BLOCK,
  runOnboarding,
  welcomeBlock,
};
