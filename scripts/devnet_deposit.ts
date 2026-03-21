/**
 * Deposit SOL to create a UserBot account on devnet.
 *
 * Usage:
 *   npx ts-node scripts/devnet_deposit.ts <wallet_json_path> [amount_sol]
 *
 * Example:
 *   npx ts-node scripts/devnet_deposit.ts target/test-wallets/wallet_user1.json 0.1
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
    console.log("Usage: npx ts-node scripts/devnet_deposit.ts <wallet_json_path> [amount_sol]");
    process.exit(1);
  }

  const walletPath = args[0];
  const amountSol = parseFloat(args[1] || "0.1");
  const amountLamports = new anchor.BN(Math.round(amountSol * LAMPORTS_PER_SOL));

  // Load user wallet
  const raw = JSON.parse(fs.readFileSync(walletPath, "utf-8"));
  const userKeypair = Keypair.fromSecretKey(Uint8Array.from(raw));

  const connection = new Connection(DEVNET_URL, "confirmed");
  const wallet = new anchor.Wallet(userKeypair);
  const provider = new anchor.AnchorProvider(connection, wallet, { commitment: "confirmed" });
  anchor.setProvider(provider);

  const program = anchor.workspace.clawChain as Program<ClawChain>;

  const [operatorConfigPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("operator_config")],
    program.programId
  );
  const [userBotPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("user_bot"), userKeypair.publicKey.toBuffer()],
    program.programId
  );

  console.log("=".repeat(60));
  console.log("ClawChain Devnet Deposit");
  console.log("=".repeat(60));
  console.log(`User Wallet: ${userKeypair.publicKey.toBase58()}`);
  console.log(`UserBot PDA: ${userBotPda.toBase58()}`);
  console.log(`Amount:      ${amountSol} SOL (${amountLamports.toString()} lamports)`);

  const balance = await connection.getBalance(userKeypair.publicKey);
  console.log(`Balance:     ${balance / LAMPORTS_PER_SOL} SOL`);

  if (balance < amountLamports.toNumber() + 10_000) {
    console.log("\nInsufficient balance. Requesting airdrop...");
    try {
      const sig = await connection.requestAirdrop(userKeypair.publicKey, 2 * LAMPORTS_PER_SOL);
      await connection.confirmTransaction(sig, "confirmed");
      const newBal = await connection.getBalance(userKeypair.publicKey);
      console.log(`New balance: ${newBal / LAMPORTS_PER_SOL} SOL`);
    } catch (err: any) {
      console.error(`Airdrop failed: ${err.message}`);
      console.log("Please fund the wallet manually and retry.");
      process.exit(1);
    }
  }

  console.log("\nSending deposit transaction...");
  try {
    const tx = await program.methods
      .deposit(amountLamports)
      .accountsStrict({
        userBot: userBotPda,
        operatorConfig: operatorConfigPda,
        owner: userKeypair.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([userKeypair])
      .rpc();
    console.log(`TX: ${tx}`);

    const userBot = await program.account.userBot.fetch(userBotPda);
    console.log("\nUserBot account state:");
    console.log(`  Owner:              ${userBot.owner.toBase58()}`);
    console.log(`  Bot Handle:         ${userBot.botHandle || "(pending)"}`);
    console.log(`  Active:             ${userBot.isActive}`);
    console.log(`  Provisioning:       ${userBot.provisioningStatus}`);
    console.log(`  Total Deposited:    ${userBot.totalDeposited.toNumber() / LAMPORTS_PER_SOL} SOL`);
  } catch (err: any) {
    console.error(`Deposit failed: ${err.message}`);
  }
}

main().catch(console.error);
