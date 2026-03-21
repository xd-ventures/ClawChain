import { Keypair, Connection, LAMPORTS_PER_SOL } from "@solana/web3.js";
import * as fs from "fs";
import * as path from "path";

const DEVNET_URL = "https://api.devnet.solana.com";
const WALLET_DIR = path.join(__dirname, "..", "target", "test-wallets");
const NUM_WALLETS = 3;
const AIRDROP_SOL = 2;

async function main() {
  const connection = new Connection(DEVNET_URL, "confirmed");

  if (!fs.existsSync(WALLET_DIR)) {
    fs.mkdirSync(WALLET_DIR, { recursive: true });
  }

  console.log("ClawChain Devnet Test Wallets");
  console.log("=".repeat(60));

  for (let i = 1; i <= NUM_WALLETS; i++) {
    const walletPath = path.join(WALLET_DIR, `wallet_user${i}.json`);

    let keypair: Keypair;
    if (fs.existsSync(walletPath)) {
      const raw = JSON.parse(fs.readFileSync(walletPath, "utf-8"));
      keypair = Keypair.fromSecretKey(Uint8Array.from(raw));
      console.log(`\nUser ${i}: loaded existing wallet`);
    } else {
      keypair = Keypair.generate();
      fs.writeFileSync(walletPath, JSON.stringify(Array.from(keypair.secretKey)));
      console.log(`\nUser ${i}: generated new wallet`);
    }

    console.log(`  Public key: ${keypair.publicKey.toBase58()}`);
    console.log(`  File: ${walletPath}`);

    const balance = await connection.getBalance(keypair.publicKey);
    console.log(`  Current balance: ${balance / LAMPORTS_PER_SOL} SOL`);

    if (balance < AIRDROP_SOL * LAMPORTS_PER_SOL) {
      try {
        console.log(`  Requesting airdrop of ${AIRDROP_SOL} SOL...`);
        const sig = await connection.requestAirdrop(
          keypair.publicKey,
          AIRDROP_SOL * LAMPORTS_PER_SOL
        );
        await connection.confirmTransaction(sig, "confirmed");
        const newBalance = await connection.getBalance(keypair.publicKey);
        console.log(`  New balance: ${newBalance / LAMPORTS_PER_SOL} SOL`);
      } catch (err: any) {
        console.log(`  Airdrop failed (rate limit?): ${err.message}`);
        console.log(`  You can manually transfer SOL to this address.`);
      }
    } else {
      console.log(`  Balance sufficient, skipping airdrop.`);
    }
  }

  console.log("\n" + "=".repeat(60));
  console.log("Done! Wallet files saved to target/test-wallets/");
}

main().catch(console.error);
