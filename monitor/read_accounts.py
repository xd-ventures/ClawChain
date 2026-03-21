#!/usr/bin/env python3
"""
ClawChain Account Monitor
Reads and displays ClawChain accounts from a Solana cluster.

Usage:
  python read_accounts.py                     # list all UserBot accounts
  python read_accounts.py --wallet <PUBKEY>   # show specific user's bot
  python read_accounts.py --config            # show OperatorConfig
  python read_accounts.py --cluster mainnet   # use mainnet (default: devnet)
"""

import argparse
import hashlib
import struct
from datetime import datetime, timezone

from solders.pubkey import Pubkey
from solana.rpc.api import Client
from solana.rpc.types import MemcmpOpts

# Program ID — update after deploying to devnet/mainnet
PROGRAM_ID = Pubkey.from_string("C1nMit7QsTGXDxb3p5EdNGDjRLQE1yDPtebSo1DA3ejX")

CLUSTER_URLS = {
    "devnet": "https://api.devnet.solana.com",
    "mainnet": "https://api.mainnet-beta.solana.com",
    "localnet": "http://localhost:8899",
}

LAMPORTS_PER_SOL = 1_000_000_000


def account_discriminator(name: str) -> bytes:
    """Compute Anchor account discriminator: first 8 bytes of SHA256("account:<Name>")."""
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]


OPERATOR_CONFIG_DISC = account_discriminator("OperatorConfig")
USER_BOT_DISC = account_discriminator("UserBot")


def deserialize_operator_config(data: bytes) -> dict:
    """Deserialize OperatorConfig account data (after 8-byte discriminator)."""
    offset = 8  # skip discriminator
    authority = Pubkey.from_bytes(data[offset : offset + 32])
    offset += 32
    treasury = Pubkey.from_bytes(data[offset : offset + 32])
    offset += 32
    billing_amount = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    min_deposit = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    bump = data[offset]
    return {
        "authority": str(authority),
        "treasury": str(treasury),
        "billing_amount": billing_amount,
        "min_deposit": min_deposit,
        "bump": bump,
    }


def deserialize_user_bot(data: bytes) -> dict:
    """Deserialize UserBot account data (after 8-byte discriminator)."""
    offset = 8  # skip discriminator
    owner = Pubkey.from_bytes(data[offset : offset + 32])
    offset += 32
    handle_len = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    bot_handle = data[offset : offset + handle_len].decode("utf-8")
    offset += handle_len
    is_active = bool(data[offset])
    offset += 1
    created_at = struct.unpack_from("<q", data, offset)[0]
    offset += 8
    last_billed_at = struct.unpack_from("<q", data, offset)[0]
    offset += 8
    total_deposited = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    total_billed = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    bump = data[offset]
    offset += 1
    provisioning_status = data[offset] if offset < len(data) else 0
    status_names = {0: "None", 1: "Locked", 2: "Ready", 3: "Failed"}
    return {
        "owner": str(owner),
        "bot_handle": bot_handle if bot_handle else "(pending provisioning)",
        "is_active": is_active,
        "created_at": created_at,
        "last_billed_at": last_billed_at,
        "total_deposited": total_deposited,
        "total_billed": total_billed,
        "bump": bump,
        "provisioning_status": status_names.get(provisioning_status, f"Unknown({provisioning_status})"),
    }


def get_operator_config_pda() -> Pubkey:
    pda, _ = Pubkey.find_program_address([b"operator_config"], PROGRAM_ID)
    return pda


def get_user_bot_pda(owner: Pubkey) -> Pubkey:
    pda, _ = Pubkey.find_program_address([b"user_bot", bytes(owner)], PROGRAM_ID)
    return pda


def format_sol(lamports: int) -> str:
    return f"{lamports / LAMPORTS_PER_SOL:.9f} SOL"


def format_timestamp(ts: int) -> str:
    if ts == 0:
        return "never"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def print_operator_config(client: Client):
    pda = get_operator_config_pda()
    resp = client.get_account_info(pda)
    account = resp.value
    if account is None:
        print("OperatorConfig not found. Program may not be initialized.")
        return

    config = deserialize_operator_config(bytes(account.data))
    print("=" * 60)
    print("OPERATOR CONFIG")
    print("=" * 60)
    print(f"  PDA:            {pda}")
    print(f"  Authority:      {config['authority']}")
    print(f"  Treasury:       {config['treasury']}")
    print(f"  Billing Amount: {format_sol(config['billing_amount'])} ({config['billing_amount']} lamports)")
    print(f"  Min Deposit:    {format_sol(config['min_deposit'])} ({config['min_deposit']} lamports)")
    print(f"  Bump:           {config['bump']}")


def print_user_bot(client: Client, pda: Pubkey, label: str = ""):
    resp = client.get_account_info(pda)
    account = resp.value
    if account is None:
        print(f"UserBot account not found at {pda}")
        return

    bot = deserialize_user_bot(bytes(account.data))
    lamports = account.lamports
    data_len = len(account.data)
    rent_resp = client.get_minimum_balance_for_rent_exemption(data_len)
    rent_exempt = rent_resp.value
    available = max(0, lamports - rent_exempt)

    header = f"USER BOT{' — ' + label if label else ''}"
    print("-" * 60)
    print(header)
    print("-" * 60)
    print(f"  PDA:              {pda}")
    print(f"  Owner:            {bot['owner']}")
    print(f"  Bot Handle:       {bot['bot_handle']}")
    print(f"  Status:           {'ACTIVE' if bot['is_active'] else 'STOPPED'}")
    print(f"  Available Balance:{format_sol(available)}")
    print(f"  Total Deposited:  {format_sol(bot['total_deposited'])}")
    print(f"  Total Billed:     {format_sol(bot['total_billed'])}")
    print(f"  Created At:       {format_timestamp(bot['created_at'])}")
    print(f"  Last Billed At:   {format_timestamp(bot['last_billed_at'])}")


def print_all_user_bots(client: Client):
    filters = [MemcmpOpts(offset=0, bytes=USER_BOT_DISC.hex())]
    resp = client.get_program_accounts(PROGRAM_ID, filters=filters)

    accounts = resp.value
    if not accounts:
        print("No UserBot accounts found.")
        return

    print("=" * 60)
    print(f"FOUND {len(accounts)} USER BOT ACCOUNT(S)")
    print("=" * 60)

    for i, keyed_account in enumerate(accounts, 1):
        pubkey = keyed_account.pubkey
        account = keyed_account.account
        bot = deserialize_user_bot(bytes(account.data))
        lamports = account.lamports
        data_len = len(account.data)
        rent_resp = client.get_minimum_balance_for_rent_exemption(data_len)
        rent_exempt = rent_resp.value
        available = max(0, lamports - rent_exempt)

        print(f"\n  [{i}] Owner: {bot['owner']}")
        print(f"      Bot Handle:  {bot['bot_handle']}")
        print(f"      Status:      {'ACTIVE' if bot['is_active'] else 'STOPPED'}")
        print(f"      Balance:     {format_sol(available)}")
        print(f"      Deposited:   {format_sol(bot['total_deposited'])}")
        print(f"      Billed:      {format_sol(bot['total_billed'])}")


def main():
    parser = argparse.ArgumentParser(description="ClawChain Account Monitor")
    parser.add_argument("--wallet", type=str, help="Show bot account for a specific wallet pubkey")
    parser.add_argument("--config", action="store_true", help="Show OperatorConfig")
    parser.add_argument(
        "--cluster",
        type=str,
        default="devnet",
        choices=["devnet", "mainnet", "localnet"],
        help="Solana cluster (default: devnet)",
    )
    args = parser.parse_args()

    client = Client(CLUSTER_URLS[args.cluster])
    print(f"Cluster: {args.cluster} ({CLUSTER_URLS[args.cluster]})")
    print(f"Program: {PROGRAM_ID}\n")

    if args.config:
        print_operator_config(client)
    elif args.wallet:
        owner = Pubkey.from_string(args.wallet)
        pda = get_user_bot_pda(owner)
        print_user_bot(client, pda, label=args.wallet)
    else:
        print_all_user_bots(client)


if __name__ == "__main__":
    main()
