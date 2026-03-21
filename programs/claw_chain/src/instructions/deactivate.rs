use anchor_lang::prelude::*;
use crate::error::ClawChainError;
use crate::state::UserBot;

#[derive(Accounts)]
pub struct Deactivate<'info> {
    #[account(
        mut,
        seeds = [b"user_bot", owner.key().as_ref()],
        bump = user_bot.bump,
        has_one = owner,
    )]
    pub user_bot: Account<'info, UserBot>,

    pub owner: Signer<'info>,
}

pub fn handle_deactivate(ctx: Context<Deactivate>) -> Result<()> {
    require!(ctx.accounts.user_bot.is_active, ClawChainError::AlreadyInactive);
    ctx.accounts.user_bot.is_active = false;
    Ok(())
}
