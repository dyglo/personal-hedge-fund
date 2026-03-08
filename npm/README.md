# `prophetaf`

Thin npm wrapper for the Prophet Forex CLI.

## Install

```bash
npm install -g prophetaf
```

## Requirements

- Node.js 18+
- Docker Desktop installed and running
- A `.env` file in the directory where you run `prophetaf`

If you do not have a `.env` file yet, use the project example:
[`.env.example`](https://github.com/dyglo/personal-hedge-fund/blob/main/.env.example)

## Usage

```bash
prophetaf
prophetaf scan
prophetaf bias
prophetaf risk --pair XAUUSD --sl 15 --risk 1
```

With no arguments, the wrapper launches `hedge-fund chat` inside the Docker image.

## Image Override

By default the wrapper uses:

```bash
ghcr.io/dyglo/personal-hedge-fund:latest
```

To override it:

```bash
PROPHETAF_IMAGE=ghcr.io/your-org/your-image:tag prophetaf
```

## What the Wrapper Does

1. Checks that Docker CLI is installed.
2. Checks that the Docker daemon is running.
3. Verifies that `.env` exists in your current directory.
4. Pulls the Prophet image if it is missing locally.
5. Runs the container with your current directory mounted at `/workspace`.

The container starts the installed `hedge-fund` Python CLI from the image, so local state written in `/workspace` persists in the directory where you launched `prophetaf`.
