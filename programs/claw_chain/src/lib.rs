use anchor_lang::prelude::*;

pub mod error;
pub mod instructions;
pub mod state;

use instructions::*;

declare_id!("C1nMit7QsTGXDxb3p5EdNGDjRLQE1yDPtebSo1DA3ejX");

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

    pub fn lock_for_provisioning(ctx: Context<LockForProvisioning>) -> Result<()> {
        instructions::lock_for_provisioning::handle_lock_for_provisioning(ctx)
    }

    pub fn refund_failed_provision(ctx: Context<RefundFailedProvision>) -> Result<()> {
        instructions::refund_failed_provision::handle_refund_failed_provision(ctx)
    }

    pub fn initialize_service_status(ctx: Context<InitializeServiceStatus>, max_instances: u16) -> Result<()> {
        instructions::initialize_service_status::handle_initialize_service_status(ctx, max_instances)
    }

    pub fn update_service_status(ctx: Context<UpdateServiceStatus>, active_instances: u16, accepting_new: bool) -> Result<()> {
        instructions::update_service_status::handle_update_service_status(ctx, active_instances, accepting_new)
    }

    pub fn force_reset(ctx: Context<ForceReset>) -> Result<()> {
        instructions::force_reset::handle_force_reset(ctx)
    }
}
