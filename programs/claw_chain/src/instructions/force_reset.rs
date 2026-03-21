use anchor_lang::prelude::*;
use crate::state::{OperatorConfig, UserBot};

#[derive(Accounts)]
pub struct ForceReset<'info> {
    #[account(
        mut,
        seeds = [b"user_bot", user_bot.owner.as_ref()],
        bump = user_bot.bump,
    )]
    pub user_bot: Account<'info, UserBot>,

    /// CHECK: The owner wallet to return funds to. Validated against user_bot.owner.
    #[account(
        mut,
        constraint = owner.key() == user_bot.owner,
    )]
    pub owner: UncheckedAccount<'info>,

    #[account(
        seeds = [b"operator_config"],
        bump = operator_config.bump,
        has_one = authority,
    )]
    pub operator_config: Account<'info, OperatorConfig>,

    pub authority: Signer<'info>,
}

pub fn handle_force_reset(ctx: Context<ForceReset>) -> Result<()> {
    let user_bot = &mut ctx.accounts.user_bot;

    // Return all available SOL to the owner
    let rent = Rent::get()?;
    let min_balance = rent.minimum_balance(user_bot.to_account_info().data_len());
    let current_lamports = user_bot.to_account_info().lamports();
    let available = current_lamports.saturating_sub(min_balance);

    if available > 0 {
        **user_bot.to_account_info().try_borrow_mut_lamports()? -= available;
        **ctx.accounts.owner.to_account_info().try_borrow_mut_lamports()? += available;
    }

    // Reset all state
    user_bot.is_active = false;
    user_bot.provisioning_status = 0;
    user_bot.bot_handle = String::new();

    Ok(())
}
