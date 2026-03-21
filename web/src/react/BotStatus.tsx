import { useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { PublicKey } from "@solana/web3.js";
import { useProgram } from "../hooks/useProgram";
import { PROGRAM_ID, LAMPORTS_PER_SOL } from "../lib/constants";
import type { UserBotState } from "../hooks/useUserBot";

interface Props {
  userBot: UserBotState;
  onAction: () => void;
}

export function BotStatus({ userBot, onAction }: Props) {
  const { publicKey } = useWallet();
  const program = useProgram();
  const [busy, setBusy] = useState(false);

  const botName = userBot.botHandle.replace("@", "");
  const telegramUrl = `https://t.me/${botName}`;

  const handleDeactivate = async () => {
    if (!publicKey || !program) return;
    setBusy(true);
    try {
      const [pda] = PublicKey.findProgramAddressSync(
        [Buffer.from("user_bot"), publicKey.toBuffer()],
        PROGRAM_ID
      );
      await program.methods.deactivate().accounts({ userBot: pda, owner: publicKey }).rpc();
      onAction();
    } catch (e: any) {
      console.error("Deactivate failed:", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bot-status">
      <h2 className="dashboard-title">Your Bot is Live!</h2>

      <div className="bot-handle-card">
        <span className="bot-handle">{userBot.botHandle}</span>
        <a href={telegramUrl} target="_blank" rel="noopener noreferrer" className="neon-btn neon-btn-cyan">
          Chat on Telegram
        </a>
      </div>

      <div className="bot-stats">
        <div className="stat">
          <span className="stat-label">Balance</span>
          <span className="stat-value">{(userBot.availableBalance / LAMPORTS_PER_SOL).toFixed(4)} SOL</span>
        </div>
        <div className="stat">
          <span className="stat-label">Deposited</span>
          <span className="stat-value">{(userBot.totalDeposited / LAMPORTS_PER_SOL).toFixed(4)} SOL</span>
        </div>
        <div className="stat">
          <span className="stat-label">Billed</span>
          <span className="stat-value">{(userBot.totalBilled / LAMPORTS_PER_SOL).toFixed(4)} SOL</span>
        </div>
      </div>

      <div className="dashboard-actions">
        <button className="neon-btn neon-btn-magenta" onClick={handleDeactivate} disabled={busy}>
          {busy ? "Stopping..." : "Stop Bot"}
        </button>
      </div>
    </div>
  );
}
