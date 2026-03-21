# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClawChain is "AI Agents as a Service, powered by Solana." Users deposit SOL via an on-chain program and receive a personal AI bot on Telegram — no accounts, no subscriptions. The MVP uses PicoClaw (<10MB RAM, single Go binary) deployed on dedicated GCP micro VMs.

## Architecture

Three main components:

1. **Solana Program (Anchor/Rust)** — On-chain state: user deposits, bot handle registry, active/stopped flags, billing transfers. Wallet-to-bot-handle mapping is intentionally public for cryptographic identity verification.
2. **Orchestrator (Python + SQLite)** — Watches blockchain for new deposits, provisions GCP container VMs, writes bot handles back on-chain, runs periodic billing loop (user -> operator account). Runs on a dedicated GCP VM with IAM permissions. Has a mock mode (YAML file backend) for testing without blockchain or GCP.
3. **PicoClaw VMs (GCP)** — Each user gets a dedicated Container-Optimized OS VM running the `docker.io/sipeed/picoclaw:latest` image with config injected via cloud-init.

## Build & Development Commands

### Solana Program (Anchor)
```bash
anchor build                          # compile the program
anchor test                           # run all 15 tests (starts local validator)
anchor deploy --provider.cluster devnet  # deploy to devnet
anchor keys list                      # show program ID
```

### Devnet Test Wallets
```bash
npx ts-node scripts/devnet_wallets.ts  # generate 3 test wallets, airdrop SOL
```
Wallets are saved to `target/test-wallets/wallet_user{1,2,3}.json`.

### Orchestrator
```bash
cd orchestrator && pip install -r requirements.txt
cp .env.example .env  # edit with your values
# Create telegram_bots.txt with pre-generated bot credentials (bot_name:bot_token per line)
python -m orchestrator.main  # run from repo root
```

Mock mode (no Solana/GCP deps needed):
```bash
MOCK_STATE_FILE=./orchestrator/mock_state.yaml \
TELEGRAM_BOTS_FILE=./orchestrator/telegram_bots.example.txt \
SQLITE_DB_PATH=/tmp/test.db \
python -m orchestrator.main
```

### Python Account Monitor
```bash
cd monitor && pip install -r requirements.txt
python read_accounts.py                     # list all UserBot accounts
python read_accounts.py --wallet <PUBKEY>   # show specific user's bot
python read_accounts.py --config            # show OperatorConfig
python read_accounts.py --cluster localnet  # use localnet instead of devnet
```

## On-Chain Data Model

Three PDA account types, all owned by the program:

- **OperatorConfig** (`seeds = [b"operator_config"]`) — singleton storing authority, treasury, billing_amount, min_deposit
- **UserBot** (`seeds = [b"user_bot", user_wallet]`) — one per user; stores owner, bot_handle, is_active flag, provisioning_status (0=None/1=Locked/2=Ready/3=Failed), timestamps, totals
- **ServiceStatus** (`seeds = [b"service_status"]`) — singleton storing active_instances, max_instances, accepting_new (written by orchestrator)

The user's available SOL balance is the PDA's lamport balance minus rent-exempt minimum — no separate balance field.

Ten instructions: `initialize`, `deposit` (init_if_needed), `set_bot_handle` (also sets provisioning_status=Ready), `deactivate`, `bill` (requires provisioning_status=Ready, auto-deactivates on insufficient funds), `withdraw_remaining`, `lock_for_provisioning`, `refund_failed_provision`, `initialize_service_status`, `update_service_status`.

## Commit Workflow

Commit each major step separately so the history is reviewable:

1. **Solana program** — Anchor scaffold, account structs, instructions, tests
2. **Devnet deployment** — program ID updates, deploy config
3. **Orchestrator** — Python backend modules (config, db, chain, gcp, cloud_init, bot_pool, main)
4. **Infrastructure changes** — VM image approach, cloud-init templates
5. **Frontend/GUI** — (future) web UI for user status

Before committing, always verify no secrets are staged: `git diff --cached --name-only` — watch for `.env`, `telegram_bots.txt`, `*-keypair.json`, `wallet_user*.json`.

## Architectural Decisions

> This section is append-only. When a decision is superseded, add a new entry
> referencing the old one. Never edit or delete previous entries — they serve as
> historical record of why things changed.

### ADR-001: PicoClaw over NemoClaw (2026-03-21)

NemoClaw (NVIDIA's enterprise OpenClaw stack) was the initial target but proved impractical for rapid iteration. PicoClaw's minimal footprint (<10MB RAM, single binary, native Telegram support) makes it ideal for spinning up isolated agent instances quickly and cheaply on micro VMs.

### ADR-002: Dedicated VMs for isolation (2026-03-21)

For the hackathon MVP, GCP micro VMs offer the simplest isolation model with acceptable cost. The production path is Kubernetes on bare metal via tf-xd-venture-talos01.

### ADR-003: SOL balance stored as PDA lamports (2026-03-21)

The user's available balance is the UserBot PDA's lamport balance minus rent-exempt minimum — no separate balance field in the account struct. Deposits transfer SOL into the PDA; billing transfers SOL out to treasury. This keeps the balance always consistent with no sync drift possible.

### ADR-004: bill auto-deactivates on insufficient funds (2026-03-21)

The `bill` instruction sets `is_active = false` when balance is insufficient instead of returning an error. This lets the orchestrator call `bill` without pre-checking balances client-side. The orchestrator detects the `is_active = false` state on the next poll and shuts down the VM.

### ADR-005: Telegram bot pool — manual pre-generation (2026-03-21)

For MVP, Telegram bots are pre-generated manually via @BotFather and stored in a text file (`bot_name:bot_token` per line). The orchestrator imports the pool into SQLite and tracks allocation. This avoids Telegram API integration complexity for the hackathon.

### ADR-006: Container-Optimized OS over custom base image (2026-03-21)

*Supersedes part of ADR-002 (custom base image approach).*

Initially planned to use a custom GCP VM image with PicoClaw installed from deb package. Changed to GCP Container-Optimized OS (cos-cloud/cos-stable) running `docker.io/sipeed/picoclaw:latest` via `gce-container-declaration` metadata. Reasons:
- No deb package available for x86_64 (only ARM)
- No base image to build or maintain
- No systemd unit to write
- Config injected via cloud-init writing to host path, bind-mounted into container

### ADR-007: Mock chain backend for testing (2026-03-21)

The orchestrator uses a `ChainBackend` abstraction (chain.py) with two implementations: `SolanaBackend` (real RPC) and `MockBackend` (YAML file). Set `MOCK_STATE_FILE` env var to activate mock mode. The mock backend re-reads the YAML on every poll (so you can edit state live) and writes back changes from set_bot_handle/bill. All heavy deps (solana, solders, google-cloud-compute) are lazy-imported so mock mode works with just pyyaml + python-dotenv.

### ADR-008: SNS domain deferred to mainnet (2026-03-21)

Solana Name Service (SNS/.sol domains) only exist on mainnet. Registration of clawchain.sol deferred until mainnet launch. No code changes needed — the on-chain data model already supports the future web GUI without modification.

### ADR-009: Capacity management with on-chain ServiceStatus (2026-03-21)

Added `MAX_INSTANCES` config to limit concurrent VMs. Orchestrator startup validates `max_instances <= bot pool size`. A new `ServiceStatus` PDA (separate from OperatorConfig to avoid reallocation) stores `active_instances`, `max_instances`, `accepting_new` on-chain for external visibility (future GUI). The orchestrator writes this every poll cycle via `update_service_status`. When at capacity, new deposits are not provisioned — funds sit until a slot opens.

### ADR-010: Escrow-like provisioning guarantee (2026-03-21)

Added `provisioning_status` field to UserBot (0=None, 1=Locked, 2=Ready, 3=Failed). Orchestrator calls `lock_for_provisioning` before creating a VM (prevents withdrawal during provisioning). If VM fails to start within ~5 min, `refund_failed_provision` deactivates the account (user can withdraw). `bill` instruction now requires `provisioning_status == 2` (Ready) — no billing until VM is confirmed healthy and bot handle is set. This is not true escrow (no 3rd party), but guarantees users are never charged for a service they didn't receive.
