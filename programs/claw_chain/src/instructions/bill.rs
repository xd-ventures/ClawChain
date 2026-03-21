use anchor_lang::prelude::*;
use crate::error::ClawChainError;
use crate::state::{OperatorConfig, UserBot};

#[derive(Accounts)]
pub struct Bill<'info> {
    #[account(
        mut,
        seeds = [b"user_bot", user_bot.owner.as_ref()],
        bump = user_bot.bump,
    )]
    pub user_bot: Account<'info, UserBot>,

    #[account(
        seeds = [b"operator_config"],
        bump = operator_config.bump,
        has_one = authority,
        has_one = treasury,
    )]
    pub operator_config: Account<'info, OperatorConfig>,

    pub authority: Signer<'info>,

    /// CHECK: Validated via has_one on operator_config.
    #[account(mut)]
    pub treasury: UncheckedAccount<'info>,
}

pub fn handle_bill(ctx: Context<Bill>) -> Result<()> {
    let user_bot = &mut ctx.accounts.user_bot;
    let config = &ctx.accounts.operator_config;

    require!(user_bot.is_active, ClawChainError::BotNotActive);

    let rent = Rent::get()?;
    let min_balance = rent.minimum_balance(user_bot.to_account_info().data_len());
    let current_lamports = user_bot.to_account_info().lamports();
    let available = current_lamports.saturating_sub(min_balance);

    // Auto-deactivate if insufficient funds
    if available < config.billing_amount {
        user_bot.is_active = false;
        return Ok(());
    }

    // Transfer lamports from PDA to treasury (program owns the PDA)
    **user_bot.to_account_info().try_borrow_mut_lamports()? -= config.billing_amount;
    **ctx.accounts.treasury.to_account_info().try_borrow_mut_lamports()? += config.billing_amount;

    user_bot.last_billed_at = Clock::get()?.unix_timestamp;
    user_bot.total_billed = user_bot.total_billed.checked_add(config.billing_amount).unwrap();

    Ok(())
}
