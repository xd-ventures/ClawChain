use anchor_lang::prelude::*;

#[error_code]
pub enum ClawChainError {
    #[msg("Deposit amount is below the minimum required")]
    DepositTooSmall,
    #[msg("Bot handle exceeds maximum length of 32 characters")]
    BotHandleTooLong,
    #[msg("Bot account is not active")]
    BotNotActive,
    #[msg("Bot account is already inactive")]
    AlreadyInactive,
    #[msg("Bot account must be deactivated before withdrawal")]
    MustDeactivateFirst,
    #[msg("Insufficient balance for billing")]
    InsufficientBalance,
    #[msg("No balance available to withdraw")]
    NothingToWithdraw,
}
