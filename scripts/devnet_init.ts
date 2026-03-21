/**
 * Initialize ClawChain program state on devnet.
 *
 * Calls:
 *   1. initialize — creates OperatorConfig (authority, treasury, billing params)
 *   2. initialize_service_status — creates ServiceStatus (capacity tracking)
 *
 * Usage:
 *   npx ts-node scripts/devnet_init.ts
 *
 * Requires: ANCHOR_WALLET=~/.config/solana/id.json (the deployer/operator wallet)
 */

import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { ClawChain } from "../target/types/claw_chain";
import { PublicKey, Keypair, Connection, LAMPORTS_PER_SOL } from "@solana/web3.js";
import * as fs from "fs";

const DEVNET_URL = "https://api.devnet.solana.com";
const BILLING_AMOUNT = new anchor.BN(10_000_000); // 0.01 SOL per billing cycle
const MIN_DEPOSIT = new anchor.BN(50_000_000);    // 0.05 SOL minimum deposit
const MAX_INSTANCES = 10;

async function main() {
  // Load operator wallet
  const walletPath = process.env.ANCHOR_WALLET || `${process.env.HOME}/.config/solana/id.json`;
  const raw = JSON.parse(fs.readFileSync(walletPath, "utf-8"));
  const operatorKeypair = Keypair.fromSecretKey(Uint8Array.from(raw));

  const connection = new Connection(DEVNET_URL, "confirmed");
  const wallet = new anchor.Wallet(operatorKeypair);
  const provider = new anchor.AnchorProvider(connection, wallet, { commitment: "confirmed" });
  anchor.setProvider(provider);

  const program = anchor.workspace.clawChain as Program<ClawChain>;

  console.log("=".repeat(60));
  console.log("ClawChain Devnet Initialization");
  console.log("=".repeat(60));
  console.log(`Program ID: ${program.programId.toBase58()}`);
  console.log(`Operator:   ${operatorKeypair.publicKey.toBase58()}`);
  console.log(`RPC:        ${DEVNET_URL}`);
  console.log();

  // Use operator wallet as both authority and treasury for MVP
  const treasury = operatorKeypair.publicKey;

  // PDAs
  const [operatorConfigPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("operator_config")],
    program.programId
  );
  const [serviceStatusPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("service_status")],
    program.programId
  );

  // --- Step 1: Initialize OperatorConfig ---
  console.log("Step 1: Initialize OperatorConfig...");
  try {
    const existing = await connection.getAccountInfo(operatorConfigPda);
    if (existing) {
      console.log("  Already initialized, skipping.");
    } else {
      const tx = await program.methods
        .initialize(BILLING_AMOUNT, MIN_DEPOSIT)
        .accountsStrict({
          operatorConfig: operatorConfigPda,
          authority: operatorKeypair.publicKey,
          treasury: treasury,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([operatorKeypair])
        .rpc();
      console.log(`  TX: ${tx}`);
    }

    const config = await program.account.operatorConfig.fetch(operatorConfigPda);
    console.log(`  Authority:      ${config.authority.toBase58()}`);
    console.log(`  Treasury:       ${config.treasury.toBase58()}`);
    console.log(`  Billing Amount: ${config.billingAmount.toNumber() / LAMPORTS_PER_SOL} SOL`);
    console.log(`  Min Deposit:    ${config.minDeposit.toNumber() / LAMPORTS_PER_SOL} SOL`);
  } catch (err: any) {
    console.error(`  Error: ${err.message}`);
  }
  console.log();

  // --- Step 2: Initialize ServiceStatus ---
  console.log("Step 2: Initialize ServiceStatus...");
  try {
    const existing = await connection.getAccountInfo(serviceStatusPda);
    if (existing) {
      console.log("  Already initialized, skipping.");
    } else {
      const tx = await program.methods
        .initializeServiceStatus(MAX_INSTANCES)
        .accountsStrict({
          serviceStatus: serviceStatusPda,
          operatorConfig: operatorConfigPda,
          authority: operatorKeypair.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([operatorKeypair])
        .rpc();
      console.log(`  TX: ${tx}`);
    }

    const status = await program.account.serviceStatus.fetch(serviceStatusPda);
    console.log(`  Active Instances: ${status.activeInstances}`);
    console.log(`  Max Instances:    ${status.maxInstances}`);
    console.log(`  Accepting New:    ${status.acceptingNew}`);
  } catch (err: any) {
    console.error(`  Error: ${err.message}`);
  }
  console.log();
  console.log("Done! Program state initialized on devnet.");
}

main().catch(console.error);
