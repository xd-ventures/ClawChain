#!/usr/bin/env python3
"""ClawChain Orchestrator — watches Solana, provisions PicoClaw VMs on GCP."""

import asyncio
import logging

from .config import Config
from .db import DB
from .chain import ChainBackend, SolanaBackend, MockBackend
from .cloud_init import generate_cloud_init, generate_container_declaration
from .bot_pool import load_bot_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("orchestrator")


async def watcher_loop(cfg: Config, db: DB, gcp, chain: ChainBackend):
    """Poll chain for new deposits and state changes."""
    while True:
        try:
            all_bots = chain.fetch_all_user_bots()
            on_chain = {b["owner"]: b for b in all_bots}

            # --- PROVISION NEW BOTS ---
            for bot in all_bots:
                if not bot["is_active"] or bot["bot_handle"] != "":
                    continue
                wallet = bot["owner"]
                existing = db.get_instance_by_wallet(wallet)
                if existing and existing["status"] in ("provisioning", "running"):
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
                        continue
                else:
                    log.info(f"[DRY-RUN] Would create VM {vm_name}")

                db.create_instance(wallet, tg_id, tg_name, vm_name, cfg.gcp_zone)

            # --- CHECK PROVISIONING -> RUNNING ---
            for inst in db.get_active_instances():
                if inst["status"] == "provisioning":
                    if gcp:
                        status = gcp.get_instance_status(inst["vm_instance_name"])
                        if status != "RUNNING":
                            continue
                        ip = gcp.get_instance_ip(inst["vm_instance_name"]) or ""
                    else:
                        # Mock mode: immediately transition to running
                        ip = "10.0.0.1"

                    db.update_instance_running(inst["wallet_pubkey"], ip)
                    log.info(f"VM {inst['vm_instance_name']} is RUNNING at {ip}")
                    _try_set_bot_handle(chain, db, inst)

                # Retry failed handle writes
                if inst["status"] == "running" and not inst["bot_handle_set_on_chain"]:
                    _try_set_bot_handle(chain, db, inst)

            # --- HANDLE REACTIVATION ---
            for bot in all_bots:
                if not bot["is_active"] or bot["bot_handle"] == "":
                    continue
                wallet = bot["owner"]
                inst = db.get_instance_by_wallet(wallet)
                if inst and inst["status"] == "stopped":
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
            for inst in db.get_active_instances():
                wallet = inst["wallet_pubkey"]
                chain_bot = on_chain.get(wallet)
                if chain_bot and not chain_bot["is_active"]:
                    log.info(f"Tearing down VM {inst['vm_instance_name']} for deactivated wallet {wallet}")
                    db.update_instance_stopping(wallet)
                    if gcp:
                        try:
                            gcp.delete_instance(inst["vm_instance_name"])
                        except Exception as e:
                            log.error(f"Failed to delete VM {inst['vm_instance_name']}: {e}")
                    else:
                        log.info(f"[DRY-RUN] Would delete VM {inst['vm_instance_name']}")
                    db.update_instance_stopped(wallet)
                    if inst["telegram_bot_id"]:
                        db.release_bot(inst["telegram_bot_id"])
                    log.info(f"VM deleted, bot released for wallet {wallet}")

        except Exception as e:
            log.exception(f"Watcher loop error: {e}")

        await asyncio.sleep(cfg.poll_interval_secs)


def _try_set_bot_handle(chain: ChainBackend, db: DB, inst: dict):
    """Try to set the bot handle on-chain for an instance."""
    bot_handle = f"@{inst['bot_name']}"
    try:
        sig = chain.set_bot_handle(inst["wallet_pubkey"], bot_handle)
        db.update_instance_bot_handle_set(inst["wallet_pubkey"])
        log.info(f"set_bot_handle confirmed for {inst['wallet_pubkey']}: {sig}")
    except Exception as e:
        log.error(f"Failed to set bot handle for {inst['wallet_pubkey']}: {e}")


async def billing_loop(cfg: Config, db: DB, chain: ChainBackend):
    """Periodically bill all active bots."""
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

    # Create chain backend (mock or real)
    if cfg.mock_state_file:
        chain: ChainBackend = MockBackend(cfg.mock_state_file)
        log.info(f"Using MOCK chain backend from {cfg.mock_state_file}")
    else:
        chain = SolanaBackend(cfg.solana_rpc_url, cfg.operator_keypair)
        log.info("Using Solana RPC chain backend")

    # Fetch operator config
    cfg.operator_config = chain.fetch_operator_config()
    log.info(
        f"Operator config: billing={cfg.operator_config['billing_amount']} lamports, "
        f"authority={cfg.operator_config['authority']}"
    )

    # Create GCP manager (None in mock mode unless GCP_PROJECT_ID is set)
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


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
