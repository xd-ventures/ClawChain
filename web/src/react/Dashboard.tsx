import { useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { PublicKey } from "@solana/web3.js";
import { useUserBot } from "../hooks/useUserBot";
import { useServiceStatus } from "../hooks/useServiceStatus";
import { useProgram } from "../hooks/useProgram";
import { PROGRAM_ID } from "../lib/constants";
import { BotStatus } from "./BotStatus";
import { DepositForm } from "./DepositForm";
import { ServiceInfo } from "./ServiceInfo";

export function Dashboard() {
  const { publicKey, connected } = useWallet();
  const userBot = useUserBot();
  const serviceStatus = useServiceStatus();

  if (!connected) {
    return (
      <div className="dashboard">
        <h2 className="dashboard-title">Connect your wallet to start</h2>
        <p className="dashboard-subtitle">
          Deposit SOL. Get a personal AI bot on Telegram. No accounts needed.
        </p>
        <div className="wallet-button-wrapper">
          <WalletMultiButton />
        </div>
        <ServiceInfo status={serviceStatus} />
      </div>
    );
  }

  if (userBot.loading) {
    return (
      <div className="dashboard">
        <div className="spinner" />
        <p className="dashboard-subtitle">Loading account...</p>
      </div>
    );
  }

  if (!userBot.exists) {
    return (
      <div className="dashboard">
        <h2 className="dashboard-title">Get Your AI Bot</h2>
        <p className="dashboard-subtitle">
          Deposit SOL to spawn a personal PicoClaw bot on Telegram.
        </p>
        <DepositForm onDeposited={userBot.refresh} />
        <ServiceInfo status={serviceStatus} />
      </div>
    );
  }

  if (userBot.isActive && userBot.botHandle && userBot.provisioningStatus === 2) {
    return (
      <div className="dashboard">
        <BotStatus userBot={userBot} onAction={userBot.refresh} />
        <ServiceInfo status={serviceStatus} />
      </div>
    );
  }

  if (userBot.isActive && userBot.provisioningStatus < 2) {
    return (
      <div className="dashboard">
        <h2 className="dashboard-title">Setting up your bot...</h2>
        <div className="spinner" />
        <p className="dashboard-subtitle">
          {userBot.provisioningStatus === 0 && "Waiting for orchestrator..."}
          {userBot.provisioningStatus === 1 && "Funds locked. Provisioning VM..."}
        </p>
        <p className="dashboard-hint">This usually takes 1-2 minutes. Page auto-refreshes.</p>
        <ServiceInfo status={serviceStatus} />
      </div>
    );
  }

  return (
    <div className="dashboard">
      <h2 className="dashboard-title">
        {userBot.provisioningStatus === 3 ? "Provisioning Failed" : "Bot Stopped"}
      </h2>
      <p className="dashboard-subtitle">
        {userBot.provisioningStatus === 3
          ? "VM failed to start. You can withdraw your deposit."
          : "Your bot has been deactivated."}
      </p>
      <div className="dashboard-actions">
        <WithdrawButton onAction={userBot.refresh} />
      </div>
      <div className="dashboard-reactivate">
        <p className="dashboard-hint">Want to start a new bot?</p>
        <DepositForm onDeposited={userBot.refresh} label="Reactivate" />
      </div>
      <ServiceInfo status={serviceStatus} />
    </div>
  );
}

function WithdrawButton({ onAction }: { onAction: () => void }) {
  const { publicKey } = useWallet();
  const program = useProgram();
  const [busy, setBusy] = useState(false);

  const handleWithdraw = async () => {
    if (!publicKey || !program) return;
    setBusy(true);
    try {
      const [pda] = PublicKey.findProgramAddressSync(
        [Buffer.from("user_bot"), publicKey.toBuffer()],
        PROGRAM_ID
      );
      await program.methods.withdrawRemaining().accounts({ userBot: pda, owner: publicKey }).rpc();
      onAction();
    } catch (e: any) {
      console.error("Withdraw failed:", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <button className="neon-btn neon-btn-magenta" onClick={handleWithdraw} disabled={busy}>
      {busy ? "Withdrawing..." : "Withdraw Deposit"}
    </button>
  );
}
