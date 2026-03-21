use anchor_lang::prelude::*;
use crate::state::{OperatorConfig, ServiceStatus};

#[derive(Accounts)]
pub struct InitializeServiceStatus<'info> {
    #[account(
        init,
        payer = authority,
        space = 8 + ServiceStatus::INIT_SPACE,
        seeds = [b"service_status"],
        bump,
    )]
    pub service_status: Account<'info, ServiceStatus>,

    #[account(
        seeds = [b"operator_config"],
        bump = operator_config.bump,
        has_one = authority,
    )]
    pub operator_config: Account<'info, OperatorConfig>,

    #[account(mut)]
    pub authority: Signer<'info>,

    pub system_program: Program<'info, System>,
}

pub fn handle_initialize_service_status(
    ctx: Context<InitializeServiceStatus>,
    max_instances: u16,
) -> Result<()> {
    let status = &mut ctx.accounts.service_status;
    status.active_instances = 0;
    status.max_instances = max_instances;
    status.accepting_new = true;
    status.last_updated = Clock::get()?.unix_timestamp;
    status.bump = ctx.bumps.service_status;
    Ok(())
}
