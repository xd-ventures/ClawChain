import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { ClawChain } from "../target/types/claw_chain";
import { expect } from "chai";
import { PublicKey, Keypair, LAMPORTS_PER_SOL } from "@solana/web3.js";

describe("claw_chain", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const program = anchor.workspace.clawChain as Program<ClawChain>;
  const connection = provider.connection;

  // Keypairs
  const operator = Keypair.generate();
  const treasury = Keypair.generate();
  const user1 = Keypair.generate();
  const user2 = Keypair.generate();
  const user3 = Keypair.generate();

  // Config values
  const billingAmount = new anchor.BN(10_000_000); // 0.01 SOL
  const minDeposit = new anchor.BN(50_000_000); // 0.05 SOL

  // PDAs
  const [operatorConfigPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("operator_config")],
    program.programId
  );

  function userBotPda(owner: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("user_bot"), owner.toBuffer()],
      program.programId
    );
  }

  async function airdrop(pubkey: PublicKey, sol: number) {
    const sig = await connection.requestAirdrop(pubkey, sol * LAMPORTS_PER_SOL);
    await connection.confirmTransaction(sig, "confirmed");
  }

  async function getBalance(pubkey: PublicKey): Promise<number> {
    return connection.getBalance(pubkey);
  }

  before(async () => {
    // Airdrop SOL to operator and users
    await airdrop(operator.publicKey, 10);
    await airdrop(user1.publicKey, 5);
    await airdrop(user2.publicKey, 5);
    await airdrop(user3.publicKey, 5);
  });

  // =========================================================================
  // Test 1: Initialize operator config
  // =========================================================================
  it("initializes operator config", async () => {
    await program.methods
      .initialize(billingAmount, minDeposit)
      .accountsStrict({
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
        treasury: treasury.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([operator])
      .rpc();

    const config = await program.account.operatorConfig.fetch(operatorConfigPda);
    expect(config.authority.toBase58()).to.equal(operator.publicKey.toBase58());
    expect(config.treasury.toBase58()).to.equal(treasury.publicKey.toBase58());
    expect(config.billingAmount.toNumber()).to.equal(10_000_000);
    expect(config.minDeposit.toNumber()).to.equal(50_000_000);
  });

  // =========================================================================
  // Test 2: Initialize again fails
  // =========================================================================
  it("fails to initialize again (already exists)", async () => {
    try {
      await program.methods
        .initialize(billingAmount, minDeposit)
        .accountsStrict({
          operatorConfig: operatorConfigPda,
          authority: operator.publicKey,
          treasury: treasury.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([operator])
        .rpc();
      expect.fail("should have thrown");
    } catch (err: any) {
      // Account already initialized - anchor will throw
      expect(err).to.exist;
    }
  });

  // =========================================================================
  // Test 3: User1 deposits and creates bot account
  // =========================================================================
  it("user1 deposits 0.1 SOL and creates bot account", async () => {
    const [pda] = userBotPda(user1.publicKey);
    const depositAmount = new anchor.BN(100_000_000); // 0.1 SOL

    await program.methods
      .deposit(depositAmount)
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        owner: user1.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([user1])
      .rpc();

    const userBot = await program.account.userBot.fetch(pda);
    expect(userBot.owner.toBase58()).to.equal(user1.publicKey.toBase58());
    expect(userBot.botHandle).to.equal("");
    expect(userBot.isActive).to.be.true;
    expect(userBot.totalDeposited.toNumber()).to.equal(100_000_000);
    expect(userBot.totalBilled.toNumber()).to.equal(0);
    expect(userBot.createdAt.toNumber()).to.be.greaterThan(0);
  });

  // =========================================================================
  // Test 4: Deposit below minimum fails
  // =========================================================================
  it("fails to deposit below minimum", async () => {
    const [pda] = userBotPda(user2.publicKey);
    const tinyAmount = new anchor.BN(1_000_000); // 0.001 SOL

    try {
      await program.methods
        .deposit(tinyAmount)
        .accountsStrict({
          userBot: pda,
          operatorConfig: operatorConfigPda,
          owner: user2.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([user2])
        .rpc();
      expect.fail("should have thrown");
    } catch (err: any) {
      expect(err.error.errorCode.code).to.equal("DepositTooSmall");
    }
  });

  // =========================================================================
  // Test 5: Operator sets bot handle
  // =========================================================================
  it("operator sets bot handle for user1", async () => {
    const [pda] = userBotPda(user1.publicKey);

    await program.methods
      .setBotHandle("@picoclaw_user1")
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
      })
      .signers([operator])
      .rpc();

    const userBot = await program.account.userBot.fetch(pda);
    expect(userBot.botHandle).to.equal("@picoclaw_user1");
  });

  // =========================================================================
  // Test 6: Non-operator cannot set bot handle
  // =========================================================================
  it("non-operator cannot set bot handle", async () => {
    const [pda] = userBotPda(user1.publicKey);

    try {
      await program.methods
        .setBotHandle("@hacker_bot")
        .accountsStrict({
          userBot: pda,
          operatorConfig: operatorConfigPda,
          authority: user1.publicKey,
        })
        .signers([user1])
        .rpc();
      expect.fail("should have thrown");
    } catch (err: any) {
      // has_one constraint violation
      expect(err).to.exist;
    }
  });

  // =========================================================================
  // Test 7: Operator bills user1
  // =========================================================================
  it("operator bills user1", async () => {
    const [pda] = userBotPda(user1.publicKey);

    const pdaBalBefore = await getBalance(pda);
    const treasuryBalBefore = await getBalance(treasury.publicKey);

    await program.methods
      .bill()
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
        treasury: treasury.publicKey,
      })
      .signers([operator])
      .rpc();

    const pdaBalAfter = await getBalance(pda);
    const treasuryBalAfter = await getBalance(treasury.publicKey);

    expect(pdaBalBefore - pdaBalAfter).to.equal(10_000_000);
    expect(treasuryBalAfter - treasuryBalBefore).to.equal(10_000_000);

    const userBot = await program.account.userBot.fetch(pda);
    expect(userBot.totalBilled.toNumber()).to.equal(10_000_000);
    expect(userBot.lastBilledAt.toNumber()).to.be.greaterThan(0);
  });

  // =========================================================================
  // Test 8: Multiple billing cycles
  // =========================================================================
  it("multiple billing cycles work correctly", async () => {
    const [pda] = userBotPda(user1.publicKey);

    await program.methods
      .bill()
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
        treasury: treasury.publicKey,
      })
      .signers([operator])
      .rpc();

    const userBot = await program.account.userBot.fetch(pda);
    expect(userBot.totalBilled.toNumber()).to.equal(20_000_000);
  });

  // =========================================================================
  // Test 9: Auto-deactivation on insufficient funds
  // =========================================================================
  it("auto-deactivates on insufficient funds", async () => {
    const [pda] = userBotPda(user3.publicKey);

    // User3 deposits exactly the minimum
    await program.methods
      .deposit(minDeposit)
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        owner: user3.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([user3])
      .rpc();

    // Bill repeatedly until auto-deactivation
    // 0.05 SOL / 0.01 SOL per billing = 5 cycles max, but rent-exempt min reduces available
    let userBot = await program.account.userBot.fetch(pda);
    while (userBot.isActive) {
      await program.methods
        .bill()
        .accountsStrict({
          userBot: pda,
          operatorConfig: operatorConfigPda,
          authority: operator.publicKey,
          treasury: treasury.publicKey,
        })
        .signers([operator])
        .rpc();

      userBot = await program.account.userBot.fetch(pda);
    }

    expect(userBot.isActive).to.be.false;
  });

  // =========================================================================
  // Test 10: User1 deactivates
  // =========================================================================
  it("user1 deactivates", async () => {
    const [pda] = userBotPda(user1.publicKey);

    await program.methods
      .deactivate()
      .accountsStrict({
        userBot: pda,
        owner: user1.publicKey,
      })
      .signers([user1])
      .rpc();

    const userBot = await program.account.userBot.fetch(pda);
    expect(userBot.isActive).to.be.false;
  });

  // =========================================================================
  // Test 11: Cannot bill inactive bot
  // =========================================================================
  it("cannot bill inactive bot", async () => {
    const [pda] = userBotPda(user1.publicKey);

    try {
      await program.methods
        .bill()
        .accountsStrict({
          userBot: pda,
          operatorConfig: operatorConfigPda,
          authority: operator.publicKey,
          treasury: treasury.publicKey,
        })
        .signers([operator])
        .rpc();
      expect.fail("should have thrown");
    } catch (err: any) {
      expect(err.error.errorCode.code).to.equal("BotNotActive");
    }
  });

  // =========================================================================
  // Test 12: User1 withdraws remaining balance
  // =========================================================================
  it("user1 withdraws remaining balance", async () => {
    const [pda] = userBotPda(user1.publicKey);

    const userBalBefore = await getBalance(user1.publicKey);
    const pdaBalBefore = await getBalance(pda);

    await program.methods
      .withdrawRemaining()
      .accountsStrict({
        userBot: pda,
        owner: user1.publicKey,
      })
      .signers([user1])
      .rpc();

    const pdaBalAfter = await getBalance(pda);
    const userBalAfter = await getBalance(user1.publicKey);

    // PDA should be at rent-exempt minimum
    const accountInfo = await connection.getAccountInfo(pda);
    const rentExempt = await connection.getMinimumBalanceForRentExemption(accountInfo!.data.length);
    expect(pdaBalAfter).to.equal(rentExempt);

    // User should have received the difference (minus tx fee)
    const withdrawn = pdaBalBefore - pdaBalAfter;
    expect(withdrawn).to.be.greaterThan(0);
  });

  // =========================================================================
  // Test 13: Cannot withdraw while active
  // =========================================================================
  it("cannot withdraw while active", async () => {
    // User2 deposits first
    const [pda] = userBotPda(user2.publicKey);

    await program.methods
      .deposit(new anchor.BN(100_000_000))
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        owner: user2.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([user2])
      .rpc();

    try {
      await program.methods
        .withdrawRemaining()
        .accountsStrict({
          userBot: pda,
          owner: user2.publicKey,
        })
        .signers([user2])
        .rpc();
      expect.fail("should have thrown");
    } catch (err: any) {
      expect(err.error.errorCode.code).to.equal("MustDeactivateFirst");
    }
  });

  // =========================================================================
  // Test 14: Reactivation via deposit
  // =========================================================================
  it("reactivates user1 via deposit", async () => {
    const [pda] = userBotPda(user1.publicKey);

    // User1 was deactivated and withdrew; re-deposit to reactivate
    await program.methods
      .deposit(new anchor.BN(100_000_000))
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        owner: user1.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([user1])
      .rpc();

    const userBot = await program.account.userBot.fetch(pda);
    expect(userBot.isActive).to.be.true;
    // total_deposited should include both deposits
    expect(userBot.totalDeposited.toNumber()).to.equal(200_000_000);
    // bot handle should still be set from before
    expect(userBot.botHandle).to.equal("@picoclaw_user1");
  });

  // =========================================================================
  // Test 15: Full lifecycle end-to-end
  // =========================================================================
  it("full lifecycle: deposit -> set handle -> bill x3 -> deactivate -> withdraw", async () => {
    // Use user2 (already has an active account from test 13)
    const [pda] = userBotPda(user2.publicKey);

    // Set bot handle
    await program.methods
      .setBotHandle("@picoclaw_user2")
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
      })
      .signers([operator])
      .rpc();

    // Bill 3 times
    for (let i = 0; i < 3; i++) {
      await program.methods
        .bill()
        .accountsStrict({
          userBot: pda,
          operatorConfig: operatorConfigPda,
          authority: operator.publicKey,
          treasury: treasury.publicKey,
        })
        .signers([operator])
        .rpc();
    }

    let userBot = await program.account.userBot.fetch(pda);
    expect(userBot.totalBilled.toNumber()).to.equal(30_000_000);
    expect(userBot.botHandle).to.equal("@picoclaw_user2");

    // Deactivate
    await program.methods
      .deactivate()
      .accountsStrict({
        userBot: pda,
        owner: user2.publicKey,
      })
      .signers([user2])
      .rpc();

    // Withdraw
    await program.methods
      .withdrawRemaining()
      .accountsStrict({
        userBot: pda,
        owner: user2.publicKey,
      })
      .signers([user2])
      .rpc();

    userBot = await program.account.userBot.fetch(pda);
    expect(userBot.isActive).to.be.false;
    expect(userBot.totalBilled.toNumber()).to.equal(30_000_000);

    // PDA at rent-exempt minimum
    const accountInfo = await connection.getAccountInfo(pda);
    const rentExempt = await connection.getMinimumBalanceForRentExemption(accountInfo!.data.length);
    const pdaBal = await getBalance(pda);
    expect(pdaBal).to.equal(rentExempt);
  });
});
