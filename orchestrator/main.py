#!/usr/bin/env python3
"""ClawChain Orchestrator — watches Solana, provisions PicoClaw VMs on GCP."""

import asyncio
import logging
import sys

from .config import Config
from .db import DB
from .chain import ChainBackend, SolanaBackend, MockBackend
from .cloud_init import generate_cloud_init, generate_container_declaration
from .bot_pool import load_bot_pool

log = logging.getLogger("orchestrator")

# Health check thresholds
MAX_PROVISION_HEALTH_FAILURES = 20   # ~5 min at 15s polls
MAX_RUNNING_HEALTH_FAILURES = 10     # ~2.5 min


def watcher_tick(cfg: Config, db: DB, gcp, chain: ChainBackend):
    """Single iteration of the watcher loop. Extracted for testability."""
    all_bots = chain.fetch_all_user_bots()
    on_chain = {b["owner"]: b for b in all_bots}

    # --- CAPACITY CHECK ---
    active_count = len(db.get_active_instances())
    at_capacity = active_count >= cfg.max_instances

    # --- PROVISION NEW BOTS ---
    for bot in all_bots:
        if not bot["is_active"] or bot["bot_handle"] != "":
            continue
        # Skip if already ready/failed (only provision if None or Locked-but-no-instance)
        ps = bot.get("provisioning_status", 0)
        if ps >= 2:
            continue  # Ready or Failed — nothing to do
        wallet = bot["owner"]
        existing = db.get_instance_by_wallet(wallet)
        if existing and existing["status"] in ("provisioning", "running"):
            continue

        if active_count >= cfg.max_instances:
            log.info(f"At capacity ({active_count}/{cfg.max_instances}), skipping {wallet}")
            continue

        if ps == 0:
            try:
                chain.lock_for_provisioning(wallet)
                log.info(f"Locked funds for provisioning: {wallet}")
            except Exception as e:
                log.error(f"Failed to lock funds for {wallet}: {e}")
                continue

        alloc = db.allocate_bot(wallet)
        if alloc is None:
            log.error("No available telegram bots in pool!")
            continue
        tg_id, tg_name, tg_token = alloc

        vm_name = f"picoclaw-{wallet[:8].lower()}"
        log.info(f"Provisioning VM {vm_name} for wallet {wallet} with bot @{tg_name}")

        if gcp:
            userdata = generate_cloud_init(cfg.openrouter_api_key, tg_token)
            container_decl = generate_container_declaration(cfg.picoclaw_image)
            try:
                gcp.create_instance(vm_name, userdata, container_decl)
            except Exception as e:
                log.error(f"Failed to create VM {vm_name}: {e}")
                db.release_bot(tg_id)
                try:
                    chain.refund_failed_provision(wallet)
                except Exception as e2:
                    log.error(f"Failed to refund {wallet} after VM creation failure: {e2}")
                continue
        else:
            log.info(f"[DRY-RUN] Would create VM {vm_name}")

        db.create_instance(wallet, tg_id, tg_name, vm_name, cfg.gcp_zone)
        active_count += 1

    # --- CHECK PROVISIONING INSTANCES ---
    for inst in db.get_active_instances():
        if inst["status"] == "provisioning":
            _handle_provisioning(cfg, db, gcp, chain, inst)

    # --- HEALTH CHECK RUNNING INSTANCES ---
    for inst in db.get_active_instances():
        if inst["status"] == "running":
            _handle_running_health(db, gcp, inst)

    # --- HANDLE REACTIVATION ---
    for bot in all_bots:
        if not bot["is_active"] or bot["bot_handle"] == "":
            continue
        wallet = bot["owner"]
        inst = db.get_instance_by_wallet(wallet)
        if inst and inst["status"] == "stopped":
            if len(db.get_active_instances()) >= cfg.max_instances:
                continue
            alloc = db.allocate_bot(wallet)
            if alloc is None:
                log.error("No available telegram bots for reactivation!")
                continue
            tg_id, tg_name, tg_token = alloc
            vm_name = f"picoclaw-{wallet[:8].lower()}-r"
            log.info(f"Re-provisioning VM {vm_name} for reactivated wallet {wallet}")

            if gcp:
                userdata = generate_cloud_init(cfg.openrouter_api_key, tg_token)
                container_decl = generate_container_declaration(cfg.picoclaw_image)
                try:
                    gcp.create_instance(vm_name, userdata, container_decl)
                except Exception as e:
                    log.error(f"Failed to re-provision VM {vm_name}: {e}")
                    db.release_bot(tg_id)
                    continue
            else:
                log.info(f"[DRY-RUN] Would create VM {vm_name}")

            db.create_instance(wallet, tg_id, tg_name, vm_name, cfg.gcp_zone)

    # --- TEARDOWN DEACTIVATED BOTS ---
    # Re-fetch on-chain state to avoid acting on stale data from before lock/provision
    fresh_bots = chain.fetch_all_user_bots()
    fresh_chain = {b["owner"]: b for b in fresh_bots}
    for inst in db.get_active_instances():
        wallet = inst["wallet_pubkey"]
        chain_bot = fresh_chain.get(wallet)
        if not chain_bot:
            continue
        # Only tear down if BOTH on-chain is inactive AND bot handle was previously set
        # (meaning the bot was running and user deactivated). Don't tear down if still
        # in provisioning flow (handle empty = never fully provisioned in this session).
        if not chain_bot["is_active"] and inst["bot_handle_set_on_chain"]:
            _teardown_instance(db, gcp, inst)

    # --- UPDATE ON-CHAIN SERVICE STATUS ---
    try:
        active_count = len(db.get_active_instances())
        accepting = active_count < cfg.max_instances
        chain.update_service_status(active_count, accepting)
    except Exception as e:
        log.warning(f"Failed to update service status on-chain: {e}")


async def watcher_loop(cfg: Config, db: DB, gcp, chain: ChainBackend):
    """Poll chain for new deposits and state changes."""
    while True:
        try:
            watcher_tick(cfg, db, gcp, chain)
        except Exception as e:
            log.exception(f"Watcher loop error: {e}")
        await asyncio.sleep(cfg.poll_interval_secs)


def _handle_provisioning(cfg: Config, db: DB, gcp, chain: ChainBackend, inst: dict):
    """Handle an instance in provisioning state: wait for VM, then health check."""
    wallet = inst["wallet_pubkey"]
    vm_name = inst["vm_instance_name"]

    if not gcp:
        db.update_instance_ip(wallet, "10.0.0.1")
        db.update_instance_running(wallet)
        log.info(f"[DRY-RUN] VM {vm_name} is RUNNING")
        _try_set_bot_handle(chain, db, inst)
        return

    if not inst["vm_ip"]:
        status = gcp.get_instance_status(vm_name)
        if status != "RUNNING":
            return
        ip = gcp.get_instance_ip(vm_name) or ""
        db.update_instance_ip(wallet, ip)
        log.info(f"VM {vm_name} is RUNNING at {ip}, waiting for container health...")
        return

    ip = inst["vm_ip"]
    if gcp.check_container_health(ip):
        db.update_instance_running(wallet)
        log.info(f"Container healthy on {vm_name} ({ip}) — setting bot handle")
        _try_set_bot_handle(chain, db, inst)
    else:
        failures = db.increment_health_failures(wallet, "Container health check failed during provisioning")
        log.warning(f"Health check failed for {vm_name} ({ip}), attempt {failures}/{MAX_PROVISION_HEALTH_FAILURES}")

        if failures >= MAX_PROVISION_HEALTH_FAILURES:
            log.error(f"Container failed to start on {vm_name} after {failures} attempts — refunding user")
            try:
                chain.refund_failed_provision(wallet)
                log.info(f"Refunded failed provision for {wallet}")
            except Exception as e:
                log.error(f"Failed to refund {wallet}: {e}")
            _teardown_instance(db, gcp, inst)


def _handle_running_health(db: DB, gcp, inst: dict):
    if not gcp or not inst["vm_ip"]:
        return

    wallet = inst["wallet_pubkey"]
    vm_name = inst["vm_instance_name"]
    ip = inst["vm_ip"]

    if gcp.check_container_health(ip):
        if inst["health_failures"] > 0:
            log.info(f"Health recovered for {vm_name} ({ip})")
            db.reset_health_failures(wallet)
    else:
        failures = db.increment_health_failures(wallet, "Container health check failed while running")
        if failures >= MAX_RUNNING_HEALTH_FAILURES:
            log.critical(f"Container unhealthy on {vm_name} ({ip}) for {failures} consecutive checks!")
        else:
            log.warning(f"Health check failed for {vm_name} ({ip}), consecutive failures: {failures}")


def _teardown_instance(db: DB, gcp, inst: dict):
    wallet = inst["wallet_pubkey"]
    vm_name = inst["vm_instance_name"]

    log.info(f"Tearing down VM {vm_name} for wallet {wallet}")
    db.update_instance_stopping(wallet)

    if gcp:
        try:
            gcp.delete_instance(vm_name)
        except Exception as e:
            log.error(f"Failed to delete VM {vm_name}: {e}")
    else:
        log.info(f"[DRY-RUN] Would delete VM {vm_name}")

    db.update_instance_stopped(wallet)
    if inst["telegram_bot_id"]:
        db.release_bot(inst["telegram_bot_id"])
    log.info(f"VM deleted, bot released for wallet {wallet}")


def _try_set_bot_handle(chain: ChainBackend, db: DB, inst: dict):
    bot_handle = f"@{inst['bot_name']}"
    try:
        sig = chain.set_bot_handle(inst["wallet_pubkey"], bot_handle)
        db.update_instance_bot_handle_set(inst["wallet_pubkey"])
        log.info(f"set_bot_handle confirmed for {inst['wallet_pubkey']}: {sig}")
    except Exception as e:
        log.error(f"Failed to set bot handle for {inst['wallet_pubkey']}: {e}")


async def billing_loop(cfg: Config, db: DB, chain: ChainBackend):
    while True:
        await asyncio.sleep(cfg.billing_interval_secs)
        try:
            instances = db.get_running_instances_for_billing()
            for inst in instances:
                wallet = inst["wallet_pubkey"]
                try:
                    sig = chain.bill(wallet)
                    db.update_last_billed(wallet)
                    log.info(f"Billed wallet {wallet}: {sig}")
                except Exception as e:
                    log.warning(f"Bill failed for {wallet}: {e}")
        except Exception as e:
            log.exception(f"Billing loop error: {e}")


async def run():
    cfg = Config.from_env()
    db = DB(cfg.sqlite_db_path)
    db.init_schema()

    # Load telegram bot pool
    bots = load_bot_pool(cfg.telegram_bots_file)
    db.import_bots(bots)
    log.info(f"Loaded {len(bots)} telegram bots, {db.get_available_bot_count()} available")

    # Startup validation
    if cfg.max_instances > len(bots):
        log.critical(
            f"MAX_INSTANCES ({cfg.max_instances}) exceeds available telegram bots ({len(bots)}). Aborting."
        )
        sys.exit(1)
    log.info(f"Max instances: {cfg.max_instances}")

    # Create chain backend
    if cfg.mock_state_file:
        chain: ChainBackend = MockBackend(cfg.mock_state_file)
        log.info(f"Using MOCK chain backend from {cfg.mock_state_file}")
    else:
        chain = SolanaBackend(cfg.solana_rpc_url, cfg.operator_keypair)
        log.info("Using Solana RPC chain backend")

    cfg.operator_config = chain.fetch_operator_config()
    log.info(
        f"Operator config: billing={cfg.operator_config['billing_amount']} lamports, "
        f"authority={cfg.operator_config['authority']}"
    )

    gcp = None
    if cfg.gcp_project_id:
        from .gcp import GCPManager
        gcp = GCPManager(
            cfg.gcp_project_id,
            cfg.gcp_zone,
            cfg.gcp_machine_type,
            cfg.gcp_network,
            cfg.gcp_service_account_email,
        )
    elif not cfg.mock_state_file:
        log.warning("GCP_PROJECT_ID not set — VM operations will be skipped")

    log.info("Orchestrator starting...")
    await asyncio.gather(
        watcher_loop(cfg, db, gcp, chain),
        billing_loop(cfg, db, chain),
    )


def setup_logging():
    """Configure logging to both console and timestamped log file."""
    from datetime import datetime
    from pathlib import Path

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    log_file = log_dir / f"{timestamp}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console: orchestrator messages only, no httpx noise
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    console.addFilter(lambda r: not r.name.startswith("httpx") and not r.name.startswith("httpcore"))
    root.addHandler(console)

    # File: everything (unbuffered so we don't lose logs on crash)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.stream.reconfigure(line_buffering=True)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return log_file


def main():
    log_file = setup_logging()
    log.info(f"Log file: {log_file}")
    asyncio.run(run())


if __name__ == "__main__":
    main()
