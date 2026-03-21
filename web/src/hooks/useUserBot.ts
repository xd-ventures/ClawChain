import { useState, useEffect, useCallback } from "react";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { PublicKey } from "@solana/web3.js";
import { useProgram } from "./useProgram";
import { PROGRAM_ID, LAMPORTS_PER_SOL } from "../lib/constants";

export interface UserBotState {
  exists: boolean;
  owner: string;
  botHandle: string;
  isActive: boolean;
  provisioningStatus: number;
  totalDeposited: number;
  totalBilled: number;
  availableBalance: number;
  loading: boolean;
}

const EMPTY: UserBotState = {
  exists: false,
  owner: "",
  botHandle: "",
  isActive: false,
  provisioningStatus: 0,
  totalDeposited: 0,
  totalBilled: 0,
  availableBalance: 0,
  loading: true,
};

export function useUserBot() {
  const { publicKey } = useWallet();
  const { connection } = useConnection();
  const program = useProgram();
  const [state, setState] = useState<UserBotState>(EMPTY);

  const refresh = useCallback(async () => {
    if (!publicKey || !program) {
      setState({ ...EMPTY, loading: false });
      return;
    }

    try {
      const [pda] = PublicKey.findProgramAddressSync(
        [Buffer.from("user_bot"), publicKey.toBuffer()],
        PROGRAM_ID
      );

      const account = await (program.account as any).userBot.fetch(pda);
      const info = await connection.getAccountInfo(pda);
      const rentExempt = await connection.getMinimumBalanceForRentExemption(info?.data.length || 111);
      const lamports = info?.lamports || 0;

      setState({
        exists: true,
        owner: account.owner.toBase58(),
        botHandle: account.botHandle || "",
        isActive: account.isActive,
        provisioningStatus: account.provisioningStatus,
        totalDeposited: account.totalDeposited.toNumber(),
        totalBilled: account.totalBilled.toNumber(),
        availableBalance: Math.max(0, lamports - rentExempt),
        loading: false,
      });
    } catch (e: any) {
      // Account doesn't exist yet
      setState({ ...EMPTY, loading: false });
    }
  }, [publicKey, program, connection]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  return { ...state, refresh };
}
