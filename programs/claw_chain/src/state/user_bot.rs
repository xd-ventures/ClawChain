use anchor_lang::prelude::*;

#[account]
#[derive(InitSpace)]
pub struct UserBot {
    /// The user's wallet address (owner of this bot account).
    pub owner: Pubkey,
    /// Telegram bot handle. Empty string means not yet provisioned.
    #[max_len(32)]
    pub bot_handle: String,
    /// Whether the bot is active.
    pub is_active: bool,
    /// Timestamp of account creation.
    pub created_at: i64,
    /// Timestamp of last billing event.
    pub last_billed_at: i64,
    /// Total amount deposited over lifetime.
    pub total_deposited: u64,
    /// Total amount billed over lifetime.
    pub total_billed: u64,
    /// PDA bump seed.
    pub bump: u8,
    /// Provisioning status: 0=None, 1=Locked, 2=Ready, 3=Failed.
    pub provisioning_status: u8,
}
