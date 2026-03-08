# `prophetaf`

Cloud CLI for the Prophet Forex backend.

## Install

```bash
npm install -g prophetaf
```

## Requirements

- Node.js 18+

## Usage

```bash
prophetaf
prophetaf chat "What is your view on XAUUSD?"
prophetaf scan
prophetaf bias
prophetaf risk --pair XAUUSD --sl 15 --risk 1
```

With no arguments, `prophetaf` starts an interactive chat session against the hosted Prophet API.

## What the Wrapper Does

1. Prints the Prophet banner.
2. Sends chat, scan, bias, and risk requests directly to the hosted API at [https://prophet-wwxjsbvhoa-uc.a.run.app](https://prophet-wwxjsbvhoa-uc.a.run.app).
3. Streams interactive chat from the hosted backend with no local Docker, Python, or `.env` setup.
