import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

PROGRAM_ID_STR = "C1nMit7QsTGXDxb3p5EdNGDjRLQE1yDPtebSo1DA3ejX"

# Lazy import — solders/solana not needed in mock mode
_PROGRAM_ID = None


def get_program_id():
    global _PROGRAM_ID
    if _PROGRAM_ID is None:
        from solders.pubkey import Pubkey
        _PROGRAM_ID = Pubkey.from_string(PROGRAM_ID_STR)
    return _PROGRAM_ID


# Re-export for backward compat with solana_rpc/solana_tx
@property
def _compat_program_id():
    return get_program_id()


@dataclass
class Config:
    solana_rpc_url: str
    gcp_project_id: str
    gcp_zone: str
    gcp_machine_type: str
    picoclaw_image: str
    gcp_network: str
    gcp_service_account_email: str
    openrouter_api_key: str
    telegram_bots_file: str
    sqlite_db_path: str
    poll_interval_secs: int
    billing_interval_secs: int
    max_instances: int
    mock_state_file: str  # if set, use MockBackend instead of Solana RPC

    # Loaded at runtime (None in mock mode)
    operator_keypair: object = field(default=None)

    # Populated at runtime after fetching from chain
    operator_config: dict = field(default_factory=dict)
    operator_config_pda: object = field(default=None)
    treasury: object = field(default=None)

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()

        mock_state_file = os.environ.get("MOCK_STATE_FILE", "")
        operator_keypair = None

        if not mock_state_file:
            # Only load Solana keypair when not in mock mode
            from solders.keypair import Keypair
            keypair_path = os.environ.get("OPERATOR_KEYPAIR_PATH", "~/.config/solana/id.json")
            keypair_path = os.path.expanduser(keypair_path)
            with open(keypair_path) as f:
                secret = json.load(f)
            operator_keypair = Keypair.from_bytes(bytes(secret))

        return cls(
            solana_rpc_url=os.environ.get("SOLANA_RPC_URL", "https://api.devnet.solana.com"),
            operator_keypair=operator_keypair,
            gcp_project_id=os.environ.get("GCP_PROJECT_ID", ""),
            gcp_zone=os.environ.get("GCP_ZONE", "europe-central2-a"),
            gcp_machine_type=os.environ.get("GCP_MACHINE_TYPE", "e2-micro"),
            picoclaw_image=os.environ.get("PICOCLAW_IMAGE", "docker.io/sipeed/picoclaw:latest"),
            gcp_network=os.environ.get("GCP_NETWORK", "sol-hack"),
            gcp_service_account_email=os.environ.get("GCP_SERVICE_ACCOUNT_EMAIL", ""),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            telegram_bots_file=os.environ.get("TELEGRAM_BOTS_FILE", "./telegram_bots.txt"),
            sqlite_db_path=os.environ.get("SQLITE_DB_PATH", "./orchestrator.db"),
            poll_interval_secs=int(os.environ.get("POLL_INTERVAL_SECS", "15")),
            billing_interval_secs=int(os.environ.get("BILLING_INTERVAL_SECS", "3600")),
            max_instances=int(os.environ.get("MAX_INSTANCES", "10")),
            mock_state_file=mock_state_file,
        )
