use anchor_lang::prelude::*;
use crate::state::{OperatorConfig, ServiceStatus};

#[derive(Accounts)]
pub struct UpdateServiceStatus<'info> {
    #[account(
        mut,
        seeds = [b"service_status"],
        bump = service_status.bump,
    )]
    pub service_status: Account<'info, ServiceStatus>,

    #[account(
        seeds = [b"operator_config"],
        bump = operator_config.bump,
        has_one = authority,
    )]
    pub operator_config: Account<'info, OperatorConfig>,

    pub authority: Signer<'info>,
}

pub fn handle_update_service_status(
    ctx: Context<UpdateServiceStatus>,
    active_instances: u16,
    accepting_new: bool,
) -> Result<()> {
    let status = &mut ctx.accounts.service_status;
    status.active_instances = active_instances;
    status.accepting_new = accepting_new;
    status.last_updated = Clock::get()?.unix_timestamp;
    Ok(())
}
