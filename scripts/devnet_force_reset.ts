/**
 * Force-reset a UserBot account on devnet (operator-only).
 * Returns all SOL to the owner, clears bot_handle, deactivates.
 *
 * Usage:
 *   npx ts-node scripts/devnet_force_reset.ts <owner_wallet_pubkey>
 *   npx ts-node scripts/devnet_force_reset.ts all    # reset ALL UserBot accounts
 */

import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { ClawChain } from "../target/types/claw_chain";
import { PublicKey, Keypair, Connection, LAMPORTS_PER_SOL } from "@solana/web3.js";
import * as fs from "fs";

const DEVNET_URL = "https://api.devnet.solana.com";

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.log("Usage: npx ts-node scripts/devnet_force_reset.ts <owner_pubkey | all>");
    process.exit(1);
  }

  const walletPath = process.env.ANCHOR_WALLET || `${process.env.HOME}/.config/solana/id.json`;
  const raw = JSON.parse(fs.readFileSync(walletPath, "utf-8"));
  const operatorKeypair = Keypair.fromSecretKey(Uint8Array.from(raw));

  const connection = new Connection(DEVNET_URL, "confirmed");
  const wallet = new anchor.Wallet(operatorKeypair);
  const provider = new anchor.AnchorProvider(connection, wallet, { commitment: "confirmed" });
  anchor.setProvider(provider);

  const program = anchor.workspace.clawChain as Program<ClawChain>;

  const [operatorConfigPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("operator_config")],
    program.programId
  );

  let owners: PublicKey[] = [];

  if (args[0] === "all") {
    // Fetch all UserBot accounts
    const accounts = await program.account.userBot.all();
    owners = accounts.map((a) => a.account.owner);
    console.log(`Found ${owners.length} UserBot account(s)`);
  } else {
    owners = [new PublicKey(args[0])];
  }

  for (const owner of owners) {
    const [pda] = PublicKey.findProgramAddressSync(
      [Buffer.from("user_bot"), owner.toBuffer()],
      program.programId
    );

    try {
      const bot = await program.account.userBot.fetch(pda);
      const info = await connection.getAccountInfo(pda);
      const rentExempt = await connection.getMinimumBalanceForRentExemption(info!.data.length);
      const available = (info!.lamports - rentExempt) / LAMPORTS_PER_SOL;

      console.log(`\n${owner.toBase58()}`);
      console.log(`  Handle: ${bot.botHandle || "(empty)"}  Active: ${bot.isActive}  PS: ${bot.provisioningStatus}`);
      console.log(`  Available: ${available.toFixed(4)} SOL`);

      const tx = await program.methods
        .forceReset()
        .accountsStrict({
          userBot: pda,
          owner: owner,
          operatorConfig: operatorConfigPda,
          authority: operatorKeypair.publicKey,
        })
        .signers([operatorKeypair])
        .rpc();
      console.log(`  Reset TX: ${tx}`);
    } catch (e: any) {
      console.log(`  Skip: ${e.message?.slice(0, 80)}`);
    }
  }

  console.log("\nDone!");
}

main().catch(console.error);
