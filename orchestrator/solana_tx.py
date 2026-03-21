"""Solana write operations: build, sign, and send transactions."""

import logging
import struct
import time

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solders.message import Message
from solana.rpc.api import Client

from .config import get_program_id
from .solana_rpc import get_operator_config_pda, get_user_bot_pda

log = logging.getLogger("orchestrator.tx")

# Instruction discriminators from IDL
SET_BOT_HANDLE_DISC = bytes([17, 239, 28, 140, 79, 144, 39, 237])
BILL_DISC = bytes([37, 50, 141, 86, 97, 228, 217, 79])


def _build_set_bot_handle_ix(
    operator_pubkey: Pubkey,
    user_bot_pda: Pubkey,
    operator_config_pda: Pubkey,
    bot_handle: str,
) -> Instruction:
    """Build the set_bot_handle instruction."""
    # Borsh-encode the string: 4-byte little-endian length + UTF-8 bytes
    handle_bytes = bot_handle.encode("utf-8")
    data = SET_BOT_HANDLE_DISC + struct.pack("<I", len(handle_bytes)) + handle_bytes

    accounts = [
        AccountMeta(pubkey=user_bot_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=operator_config_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=operator_pubkey, is_signer=True, is_writable=False),
    ]
    return Instruction(program_id=get_program_id(), data=data, accounts=accounts)


def _build_bill_ix(
    operator_pubkey: Pubkey,
    user_bot_pda: Pubkey,
    operator_config_pda: Pubkey,
    treasury: Pubkey,
) -> Instruction:
    """Build the bill instruction."""
    accounts = [
        AccountMeta(pubkey=user_bot_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=operator_config_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=operator_pubkey, is_signer=True, is_writable=False),
        AccountMeta(pubkey=treasury, is_signer=False, is_writable=True),
    ]
    return Instruction(program_id=get_program_id(), data=BILL_DISC, accounts=accounts)


def _send_and_confirm(client: Client, ix: Instruction, signer: Keypair, max_retries: int = 3) -> str:
    """Send a transaction with retry logic. Returns signature string."""
    for attempt in range(max_retries):
        try:
            blockhash_resp = client.get_latest_blockhash()
            blockhash = blockhash_resp.value.blockhash

            msg = Message.new_with_blockhash([ix], signer.pubkey(), blockhash)
            tx = Transaction.new_unsigned(msg)
            tx.sign([signer], blockhash)

            resp = client.send_transaction(tx)
            sig = resp.value
            log.info(f"Transaction sent: {sig}")

            # Wait for confirmation
            client.confirm_transaction(sig, commitment="confirmed")
            return str(sig)

        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log.warning(f"TX attempt {attempt + 1} failed: {e}, retrying in {wait}s")
                time.sleep(wait)
            else:
                raise

    raise RuntimeError("unreachable")


def send_set_bot_handle(
    client: Client,
    operator_keypair: Keypair,
    user_wallet_pubkey: str,
    bot_handle: str,
    operator_config_pda: Pubkey,
    operator_config: dict,
) -> str:
    """Set the bot handle on-chain for a user. Returns tx signature."""
    owner = Pubkey.from_string(user_wallet_pubkey)
    user_bot_pda = get_user_bot_pda(owner)

    ix = _build_set_bot_handle_ix(
        operator_pubkey=operator_keypair.pubkey(),
        user_bot_pda=user_bot_pda,
        operator_config_pda=operator_config_pda,
        bot_handle=bot_handle,
    )
    return _send_and_confirm(client, ix, operator_keypair)


def send_bill(
    client: Client,
    operator_keypair: Keypair,
    user_wallet_pubkey: str,
    operator_config_pda: Pubkey,
    operator_config: dict,
) -> str:
    """Bill a user on-chain. Returns tx signature."""
    owner = Pubkey.from_string(user_wallet_pubkey)
    user_bot_pda = get_user_bot_pda(owner)
    treasury = Pubkey.from_string(operator_config["treasury"])

    ix = _build_bill_ix(
        operator_pubkey=operator_keypair.pubkey(),
        user_bot_pda=user_bot_pda,
        operator_config_pda=operator_config_pda,
        treasury=treasury,
    )
    return _send_and_confirm(client, ix, operator_keypair)
