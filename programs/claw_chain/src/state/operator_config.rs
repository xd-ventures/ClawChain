use anchor_lang::prelude::*;

#[account]
#[derive(InitSpace)]
pub struct OperatorConfig {
    /// The authority wallet that can call operator-only instructions (set_bot_handle, bill).
    pub authority: Pubkey,
    /// The wallet that receives billing payments.
    pub treasury: Pubkey,
    /// Billing amount per cycle in lamports.
    pub billing_amount: u64,
    /// Minimum deposit required to create a bot account, in lamports.
    pub min_deposit: u64,
    /// PDA bump seed.
    pub bump: u8,
}
