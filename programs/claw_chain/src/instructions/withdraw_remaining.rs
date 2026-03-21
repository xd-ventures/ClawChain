use anchor_lang::prelude::*;
use crate::error::ClawChainError;
use crate::state::UserBot;

#[derive(Accounts)]
pub struct WithdrawRemaining<'info> {
    #[account(
        mut,
        seeds = [b"user_bot", owner.key().as_ref()],
        bump = user_bot.bump,
        has_one = owner,
    )]
    pub user_bot: Account<'info, UserBot>,

    #[account(mut)]
    pub owner: Signer<'info>,
}

pub fn handle_withdraw_remaining(ctx: Context<WithdrawRemaining>) -> Result<()> {
    let user_bot = &mut ctx.accounts.user_bot;

    require!(!user_bot.is_active, ClawChainError::MustDeactivateFirst);

    let rent = Rent::get()?;
    let min_balance = rent.minimum_balance(user_bot.to_account_info().data_len());
    let current_lamports = user_bot.to_account_info().lamports();
    let available = current_lamports.saturating_sub(min_balance);

    require!(available > 0, ClawChainError::NothingToWithdraw);

    // Transfer lamports from PDA to owner (program owns the PDA)
    **user_bot.to_account_info().try_borrow_mut_lamports()? -= available;
    **ctx.accounts.owner.to_account_info().try_borrow_mut_lamports()? += available;

    Ok(())
}
