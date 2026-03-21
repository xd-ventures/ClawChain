use anchor_lang::prelude::*;

pub mod error;
pub mod instructions;
pub mod state;

use instructions::*;

declare_id!("5jKteEpinwgQaHbAZBdYRCqAEbHcS9UnL6zDw7pJYaYd");

#[program]
pub mod claw_chain {
    use super::*;

    pub fn initialize(
        ctx: Context<Initialize>,
        billing_amount: u64,
        min_deposit: u64,
    ) -> Result<()> {
        instructions::initialize::handle_initialize(ctx, billing_amount, min_deposit)
    }

    pub fn deposit(ctx: Context<Deposit>, amount: u64) -> Result<()> {
        instructions::deposit::handle_deposit(ctx, amount)
    }

    pub fn set_bot_handle(ctx: Context<SetBotHandle>, bot_handle: String) -> Result<()> {
        instructions::set_bot_handle::handle_set_bot_handle(ctx, bot_handle)
    }

    pub fn deactivate(ctx: Context<Deactivate>) -> Result<()> {
        instructions::deactivate::handle_deactivate(ctx)
    }

    pub fn bill(ctx: Context<Bill>) -> Result<()> {
        instructions::bill::handle_bill(ctx)
    }

    pub fn withdraw_remaining(ctx: Context<WithdrawRemaining>) -> Result<()> {
        instructions::withdraw_remaining::handle_withdraw_remaining(ctx)
    }
}
