use anchor_lang::prelude::*;
use crate::error::ClawChainError;
use crate::state::{OperatorConfig, UserBot};

#[derive(Accounts)]
pub struct SetBotHandle<'info> {
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
    )]
    pub operator_config: Account<'info, OperatorConfig>,

    pub authority: Signer<'info>,
}

pub fn handle_set_bot_handle(ctx: Context<SetBotHandle>, bot_handle: String) -> Result<()> {
    require!(bot_handle.len() <= 32, ClawChainError::BotHandleTooLong);
    require!(ctx.accounts.user_bot.is_active, ClawChainError::BotNotActive);

    ctx.accounts.user_bot.bot_handle = bot_handle;
    Ok(())
}
