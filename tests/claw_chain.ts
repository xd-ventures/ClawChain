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

  const [serviceStatusPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("service_status")],
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
      expect(err).to.exist;
    }
  });

  // =========================================================================
  // Test 3: User1 deposits and creates bot account
  // =========================================================================
  it("user1 deposits 0.1 SOL and creates bot account", async () => {
    const [pda] = userBotPda(user1.publicKey);

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
    expect(userBot.owner.toBase58()).to.equal(user1.publicKey.toBase58());
    expect(userBot.botHandle).to.equal("");
    expect(userBot.isActive).to.be.true;
    expect(userBot.totalDeposited.toNumber()).to.equal(100_000_000);
    expect(userBot.provisioningStatus).to.equal(0); // None
  });

  // =========================================================================
  // Test 4: Deposit below minimum fails
  // =========================================================================
  it("fails to deposit below minimum", async () => {
    const [pda] = userBotPda(user2.publicKey);

    try {
      await program.methods
        .deposit(new anchor.BN(1_000_000))
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
  // Test 5: Operator sets bot handle (also sets provisioningStatus=Ready)
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
    expect(userBot.provisioningStatus).to.equal(2); // Ready
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
      expect(err).to.exist;
    }
  });

  // =========================================================================
  // Test 7: Operator bills user1 (provisioningStatus=Ready required)
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

    // Must set bot handle first (bill requires provisioningStatus=Ready)
    await program.methods
      .setBotHandle("@picoclaw_user3")
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
      })
      .signers([operator])
      .rpc();

    // Bill repeatedly until auto-deactivation
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
  // Test 10: User1 deactivates (resets provisioningStatus)
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
    expect(userBot.provisioningStatus).to.equal(0); // Reset
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

    await program.methods
      .withdrawRemaining()
      .accountsStrict({
        userBot: pda,
        owner: user1.publicKey,
      })
      .signers([user1])
      .rpc();

    const accountInfo = await connection.getAccountInfo(pda);
    const rentExempt = await connection.getMinimumBalanceForRentExemption(accountInfo!.data.length);
    const pdaBal = await getBalance(pda);
    expect(pdaBal).to.equal(rentExempt);
  });

  // =========================================================================
  // Test 13: Cannot withdraw while active
  // =========================================================================
  it("cannot withdraw while active", async () => {
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
  // Test 14: Reactivation via deposit (resets provisioningStatus)
  // =========================================================================
  it("reactivates user1 via deposit", async () => {
    const [pda] = userBotPda(user1.publicKey);

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
    expect(userBot.totalDeposited.toNumber()).to.equal(200_000_000);
    expect(userBot.provisioningStatus).to.equal(0); // Reset on reactivation
  });

  // =========================================================================
  // Test 15: Full lifecycle
  // =========================================================================
  it("full lifecycle: deposit -> set handle -> bill x3 -> deactivate -> withdraw", async () => {
    const [pda] = userBotPda(user2.publicKey);

    // Set bot handle (makes it Ready for billing)
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
    expect(userBot.provisioningStatus).to.equal(2); // Ready

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
    expect(userBot.provisioningStatus).to.equal(0); // Reset on deactivation
  });

  // =========================================================================
  // Test 16: Initialize service status
  // =========================================================================
  it("initializes service status", async () => {
    await program.methods
      .initializeServiceStatus(10)
      .accountsStrict({
        serviceStatus: serviceStatusPda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([operator])
      .rpc();

    const status = await program.account.serviceStatus.fetch(serviceStatusPda);
    expect(status.activeInstances).to.equal(0);
    expect(status.maxInstances).to.equal(10);
    expect(status.acceptingNew).to.be.true;
  });

  // =========================================================================
  // Test 17: Update service status
  // =========================================================================
  it("updates service status", async () => {
    await program.methods
      .updateServiceStatus(5, true)
      .accountsStrict({
        serviceStatus: serviceStatusPda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
      })
      .signers([operator])
      .rpc();

    const status = await program.account.serviceStatus.fetch(serviceStatusPda);
    expect(status.activeInstances).to.equal(5);
    expect(status.acceptingNew).to.be.true;
  });

  // =========================================================================
  // Test 18: Non-operator cannot update service status
  // =========================================================================
  it("non-operator cannot update service status", async () => {
    try {
      await program.methods
        .updateServiceStatus(99, false)
        .accountsStrict({
          serviceStatus: serviceStatusPda,
          operatorConfig: operatorConfigPda,
          authority: user1.publicKey,
        })
        .signers([user1])
        .rpc();
      expect.fail("should have thrown");
    } catch (err: any) {
      expect(err).to.exist;
    }
  });

  // =========================================================================
  // Test 19: Lock for provisioning
  // =========================================================================
  it("lock for provisioning sets status to Locked", async () => {
    // User1 is active with provisioningStatus=0 from test 14
    const [pda] = userBotPda(user1.publicKey);

    await program.methods
      .lockForProvisioning()
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
      })
      .signers([operator])
      .rpc();

    const userBot = await program.account.userBot.fetch(pda);
    expect(userBot.provisioningStatus).to.equal(1); // Locked
  });

  // =========================================================================
  // Test 20: Cannot bill while locked (provisioningStatus=1)
  // =========================================================================
  it("cannot bill while locked", async () => {
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
      expect(err.error.errorCode.code).to.equal("BotNotReady");
    }
  });

  // =========================================================================
  // Test 21: Cannot bill with provisioningStatus=None
  // =========================================================================
  it("cannot bill with provisioningStatus=None", async () => {
    // User2 was deactivated in test 15, reactivate with fresh deposit
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

    // provisioningStatus=0 (None) — bill should fail
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
      expect(err.error.errorCode.code).to.equal("BotNotReady");
    }
  });

  // =========================================================================
  // Test 22: Refund failed provision
  // =========================================================================
  it("refund failed provision deactivates and sets status=Failed", async () => {
    // User1 is locked (provisioningStatus=1) from test 19
    const [pda] = userBotPda(user1.publicKey);

    await program.methods
      .refundFailedProvision()
      .accountsStrict({
        userBot: pda,
        operatorConfig: operatorConfigPda,
        authority: operator.publicKey,
      })
      .signers([operator])
      .rpc();

    const userBot = await program.account.userBot.fetch(pda);
    expect(userBot.isActive).to.be.false;
    expect(userBot.provisioningStatus).to.equal(3); // Failed
  });

  // =========================================================================
  // Test 23: User can withdraw after failed provision
  // =========================================================================
  it("user can withdraw after failed provision", async () => {
    const [pda] = userBotPda(user1.publicKey);

    const userBalBefore = await getBalance(user1.publicKey);

    await program.methods
      .withdrawRemaining()
      .accountsStrict({
        userBot: pda,
        owner: user1.publicKey,
      })
      .signers([user1])
      .rpc();

    const userBalAfter = await getBalance(user1.publicKey);
    expect(userBalAfter).to.be.greaterThan(userBalBefore - 10_000); // minus tx fee
  });

  // =========================================================================
  // Test 24: Lock requires active bot
  // =========================================================================
  it("lock requires active bot", async () => {
    // User1 is inactive (from test 22 refund)
    const [pda] = userBotPda(user1.publicKey);

    try {
      await program.methods
        .lockForProvisioning()
        .accountsStrict({
          userBot: pda,
          operatorConfig: operatorConfigPda,
          authority: operator.publicKey,
        })
        .signers([operator])
        .rpc();
      expect.fail("should have thrown");
    } catch (err: any) {
      expect(err.error.errorCode.code).to.equal("BotNotActive");
    }
  });

  // =========================================================================
  // Test 25: Refund requires locked status
  // =========================================================================
  it("refund requires locked status", async () => {
    // User2 is active with provisioningStatus=0 (from test 21 deposit)
    const [pda] = userBotPda(user2.publicKey);

    try {
      await program.methods
        .refundFailedProvision()
        .accountsStrict({
          userBot: pda,
          operatorConfig: operatorConfigPda,
          authority: operator.publicKey,
        })
        .signers([operator])
        .rpc();
      expect.fail("should have thrown");
    } catch (err: any) {
      expect(err.error.errorCode.code).to.equal("NotInProvisioningState");
    }
  });
});
