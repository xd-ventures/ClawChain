use anchor_lang::prelude::*;
use crate::error::ClawChainError;
use crate::state::{OperatorConfig, UserBot};

#[derive(Accounts)]
pub struct RefundFailedProvision<'info> {
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

pub fn handle_refund_failed_provision(ctx: Context<RefundFailedProvision>) -> Result<()> {
    let user_bot = &mut ctx.accounts.user_bot;
    require!(user_bot.is_active, ClawChainError::BotNotActive);
    require!(user_bot.provisioning_status == 1, ClawChainError::NotInProvisioningState);
    user_bot.is_active = false;
    user_bot.provisioning_status = 3; // Failed
    Ok(())
}
