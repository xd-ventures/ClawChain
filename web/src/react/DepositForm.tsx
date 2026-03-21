import { useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { PublicKey } from "@solana/web3.js";
import { BN } from "@coral-xyz/anchor";
import { useProgram } from "../hooks/useProgram";
import { PROGRAM_ID, LAMPORTS_PER_SOL } from "../lib/constants";

interface Props {
  onDeposited: () => void;
  label?: string;
}

export function DepositForm({ onDeposited, label = "Deposit SOL" }: Props) {
  const { publicKey } = useWallet();
  const program = useProgram();
  const [amount, setAmount] = useState("0.1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const handleDeposit = async () => {
    if (!publicKey || !program) return;
    setError("");
    setBusy(true);
    try {
      const lamports = new BN(Math.round(parseFloat(amount) * LAMPORTS_PER_SOL));
      const [userBotPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("user_bot"), publicKey.toBuffer()],
        PROGRAM_ID
      );
      const [operatorConfigPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("operator_config")],
        PROGRAM_ID
      );

      await program.methods
        .deposit(lamports)
        .accounts({
          userBot: userBotPda,
          operatorConfig: operatorConfigPda,
          owner: publicKey,
        })
        .rpc();
      onDeposited();
    } catch (e: any) {
      setError(e.message || "Deposit failed");
      console.error("Deposit failed:", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="deposit-form">
      <div className="deposit-input-row">
        <input
          type="number"
          step="0.01"
          min="0.05"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="deposit-input"
          placeholder="Amount in SOL"
        />
        <span className="deposit-unit">SOL</span>
      </div>
      <button className="neon-btn neon-btn-cyan" onClick={handleDeposit} disabled={busy}>
        {busy ? "Confirming..." : label}
      </button>
      {error && <p className="deposit-error">{error}</p>}
      <p className="deposit-hint">Minimum deposit: 0.05 SOL</p>
    </div>
  );
}
