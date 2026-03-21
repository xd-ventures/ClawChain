import sqlite3
from datetime import datetime, timezone


class DB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def init_schema(self):
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS telegram_bots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name TEXT NOT NULL UNIQUE,
                    bot_token TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    assigned_to TEXT,
                    assigned_at TEXT
                );

                CREATE TABLE IF NOT EXISTS instances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet_pubkey TEXT NOT NULL,
                    telegram_bot_id INTEGER REFERENCES telegram_bots(id),
                    bot_name TEXT,
                    vm_instance_name TEXT,
                    vm_zone TEXT,
                    vm_ip TEXT,
                    status TEXT NOT NULL DEFAULT 'provisioning',
                    bot_handle_set_on_chain INTEGER NOT NULL DEFAULT 0,
                    health_failures INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    stopped_at TEXT,
                    last_billed_at TEXT,
                    error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_instances_wallet ON instances(wallet_pubkey);
                CREATE INDEX IF NOT EXISTS idx_instances_status ON instances(status);
            """)

    def import_bots(self, bots: list[tuple[str, str]]):
        """Upsert bot pool from parsed file. Idempotent."""
        with self.conn:
            for name, token in bots:
                self.conn.execute(
                    """INSERT INTO telegram_bots (bot_name, bot_token)
                       VALUES (?, ?)
                       ON CONFLICT(bot_name) DO UPDATE SET bot_token=excluded.bot_token""",
                    (name, token),
                )

    def allocate_bot(self, wallet_pubkey: str) -> tuple[int, str, str] | None:
        """Pick an available bot, mark in_use. Returns (id, bot_name, bot_token) or None."""
        with self.conn:
            row = self.conn.execute(
                "SELECT id, bot_name, bot_token FROM telegram_bots WHERE status='available' LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            now = datetime.now(timezone.utc).isoformat()
            self.conn.execute(
                "UPDATE telegram_bots SET status='in_use', assigned_to=?, assigned_at=? WHERE id=?",
                (wallet_pubkey, now, row["id"]),
            )
            return row["id"], row["bot_name"], row["bot_token"]

    def release_bot(self, telegram_bot_id: int):
        with self.conn:
            self.conn.execute(
                "UPDATE telegram_bots SET status='available', assigned_to=NULL, assigned_at=NULL WHERE id=?",
                (telegram_bot_id,),
            )

    def get_available_bot_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as c FROM telegram_bots WHERE status='available'").fetchone()
        return row["c"]

    def create_instance(self, wallet_pubkey: str, telegram_bot_id: int, bot_name: str,
                        vm_instance_name: str, vm_zone: str):
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                """INSERT INTO instances
                   (wallet_pubkey, telegram_bot_id, bot_name, vm_instance_name, vm_zone, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'provisioning', ?)""",
                (wallet_pubkey, telegram_bot_id, bot_name, vm_instance_name, vm_zone, now),
            )

    def update_instance_ip(self, wallet_pubkey: str, vm_ip: str):
        """Store IP once VM is RUNNING but before health check passes."""
        with self.conn:
            self.conn.execute(
                "UPDATE instances SET vm_ip=? WHERE wallet_pubkey=? AND status='provisioning'",
                (vm_ip, wallet_pubkey),
            )

    def update_instance_running(self, wallet_pubkey: str):
        """Transition to running after health check passes."""
        with self.conn:
            self.conn.execute(
                "UPDATE instances SET status='running', health_failures=0 WHERE wallet_pubkey=? AND status='provisioning'",
                (wallet_pubkey,),
            )

    def increment_health_failures(self, wallet_pubkey: str, error_msg: str) -> int:
        """Increment health failure counter. Returns new count."""
        with self.conn:
            self.conn.execute(
                "UPDATE instances SET health_failures=health_failures+1, error_message=? WHERE wallet_pubkey=? AND status IN ('provisioning','running')",
                (error_msg, wallet_pubkey),
            )
            row = self.conn.execute(
                "SELECT health_failures FROM instances WHERE wallet_pubkey=? ORDER BY id DESC LIMIT 1",
                (wallet_pubkey,),
            ).fetchone()
            return row["health_failures"] if row else 0

    def reset_health_failures(self, wallet_pubkey: str):
        with self.conn:
            self.conn.execute(
                "UPDATE instances SET health_failures=0, error_message=NULL WHERE wallet_pubkey=? AND status='running'",
                (wallet_pubkey,),
            )

    def update_instance_bot_handle_set(self, wallet_pubkey: str):
        with self.conn:
            self.conn.execute(
                "UPDATE instances SET bot_handle_set_on_chain=1 WHERE wallet_pubkey=? AND status='running'",
                (wallet_pubkey,),
            )

    def update_instance_stopping(self, wallet_pubkey: str):
        with self.conn:
            self.conn.execute(
                "UPDATE instances SET status='stopping' WHERE wallet_pubkey=? AND status IN ('provisioning','running')",
                (wallet_pubkey,),
            )

    def update_instance_stopped(self, wallet_pubkey: str):
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE instances SET status='stopped', stopped_at=? WHERE wallet_pubkey=? AND status='stopping'",
                (now, wallet_pubkey),
            )

    def update_last_billed(self, wallet_pubkey: str):
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE instances SET last_billed_at=? WHERE wallet_pubkey=? AND status='running'",
                (now, wallet_pubkey),
            )

    def get_active_instances(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM instances WHERE status IN ('provisioning', 'running')"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_instance_by_wallet(self, wallet_pubkey: str) -> dict | None:
        """Get the most recent instance for a wallet."""
        row = self.conn.execute(
            "SELECT * FROM instances WHERE wallet_pubkey=? ORDER BY id DESC LIMIT 1",
            (wallet_pubkey,),
        ).fetchone()
        return dict(row) if row else None

    def get_running_instances_for_billing(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM instances WHERE status='running' AND bot_handle_set_on_chain=1"
        ).fetchall()
        return [dict(r) for r in rows]
