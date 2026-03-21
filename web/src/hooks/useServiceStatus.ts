import { useState, useEffect } from "react";
import { useConnection } from "@solana/wallet-adapter-react";
import { PublicKey } from "@solana/web3.js";
import { useProgram } from "./useProgram";
import { PROGRAM_ID } from "../lib/constants";

export interface ServiceStatusState {
  activeInstances: number;
  maxInstances: number;
  acceptingNew: boolean;
  loading: boolean;
}

export function useServiceStatus() {
  const { connection } = useConnection();
  const program = useProgram();
  const [state, setState] = useState<ServiceStatusState>({
    activeInstances: 0,
    maxInstances: 0,
    acceptingNew: true,
    loading: true,
  });

  useEffect(() => {
    if (!program) return;

    const fetch = async () => {
      try {
        const [pda] = PublicKey.findProgramAddressSync(
          [Buffer.from("service_status")],
          PROGRAM_ID
        );
        const account = await (program.account as any).serviceStatus.fetch(pda);
        setState({
          activeInstances: account.activeInstances,
          maxInstances: account.maxInstances,
          acceptingNew: account.acceptingNew,
          loading: false,
        });
      } catch {
        setState((s) => ({ ...s, loading: false }));
      }
    };

    fetch();
    const interval = setInterval(fetch, 15000);
    return () => clearInterval(interval);
  }, [program]);

  return state;
}
