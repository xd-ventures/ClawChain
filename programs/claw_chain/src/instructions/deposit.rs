use anchor_lang::prelude::*;
use anchor_lang::system_program;
use crate::error::ClawChainError;
use crate::state::{OperatorConfig, UserBot};

#[derive(Accounts)]
pub struct Deposit<'info> {
    #[account(
        init_if_needed,
        payer = owner,
        space = 8 + UserBot::INIT_SPACE,
        seeds = [b"user_bot", owner.key().as_ref()],
        bump,
    )]
    pub user_bot: Account<'info, UserBot>,

    #[account(
        seeds = [b"operator_config"],
        bump = operator_config.bump,
    )]
    pub operator_config: Account<'info, OperatorConfig>,

    #[account(mut)]
    pub owner: Signer<'info>,

    pub system_program: Program<'info, System>,
}

pub fn handle_deposit(ctx: Context<Deposit>, amount: u64) -> Result<()> {
    let user_bot = &mut ctx.accounts.user_bot;
    let config = &ctx.accounts.operator_config;

    // First-time creation: owner is default (all zeros)
    let is_new = user_bot.owner == Pubkey::default();

    if is_new {
        require!(amount >= config.min_deposit, ClawChainError::DepositTooSmall);
        let now = Clock::get()?.unix_timestamp;
        user_bot.owner = ctx.accounts.owner.key();
        user_bot.bot_handle = String::new();
        user_bot.is_active = true;
        user_bot.created_at = now;
        user_bot.last_billed_at = now;
        user_bot.total_deposited = 0;
        user_bot.total_billed = 0;
        user_bot.bump = ctx.bumps.user_bot;
        user_bot.provisioning_status = 0; // None
    } else {
        // Reactivation on top-up
        if !user_bot.is_active {
            user_bot.is_active = true;
            user_bot.provisioning_status = 0; // Reset on reactivation
        }
    }

    // Transfer SOL from owner to the UserBot PDA
    system_program::transfer(
        CpiContext::new(
            ctx.accounts.system_program.to_account_info(),
            system_program::Transfer {
                from: ctx.accounts.owner.to_account_info(),
                to: user_bot.to_account_info(),
            },
        ),
        amount,
    )?;

    user_bot.total_deposited = user_bot.total_deposited.checked_add(amount).unwrap();

    Ok(())
}
