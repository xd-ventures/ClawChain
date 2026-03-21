use anchor_lang::prelude::*;
use crate::state::OperatorConfig;

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(
        init,
        payer = authority,
        space = 8 + OperatorConfig::INIT_SPACE,
        seeds = [b"operator_config"],
        bump,
    )]
    pub operator_config: Account<'info, OperatorConfig>,

    #[account(mut)]
    pub authority: Signer<'info>,

    /// CHECK: Just a destination wallet for billing payments.
    pub treasury: UncheckedAccount<'info>,

    pub system_program: Program<'info, System>,
}

pub fn handle_initialize(ctx: Context<Initialize>, billing_amount: u64, min_deposit: u64) -> Result<()> {
    let config = &mut ctx.accounts.operator_config;
    config.authority = ctx.accounts.authority.key();
    config.treasury = ctx.accounts.treasury.key();
    config.billing_amount = billing_amount;
    config.min_deposit = min_deposit;
    config.bump = ctx.bumps.operator_config;
    Ok(())
}
