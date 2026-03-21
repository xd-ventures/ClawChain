use anchor_lang::prelude::*;

#[account]
#[derive(InitSpace)]
pub struct ServiceStatus {
    /// Number of currently active instances.
    pub active_instances: u16,
    /// Maximum instances the service supports.
    pub max_instances: u16,
    /// Whether the service is accepting new signups.
    pub accepting_new: bool,
    /// Unix timestamp of last update.
    pub last_updated: i64,
    /// PDA bump seed.
    pub bump: u8,
}
