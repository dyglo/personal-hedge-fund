#!/usr/bin/env node

const { runCli, UserError } = require("../lib/runner");

async function main() {
  try {
    const exitCode = await runCli({
      argv: process.argv.slice(2),
      cwd: process.cwd(),
      env: process.env,
      stdin: process.stdin,
      stdout: process.stdout,
      console,
    });
    process.exitCode = typeof exitCode === "number" ? exitCode : 0;
  } catch (error) {
    if (error instanceof UserError) {
      console.error(`prophetaf: ${error.message}`);
      process.exitCode = error.exitCode;
      return;
    }

    const message = error instanceof Error ? error.message : String(error);
    console.error(`prophetaf: ${message}`);
    process.exitCode = 1;
  }
}

main();
