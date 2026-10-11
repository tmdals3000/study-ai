import { useCallback, useEffect, useRef, useState } from "react";
import { api, type GenerateOptions, type Generation, type Kind } from "../api";
export function useGeneration<T>(docId: number, kind: Kind) {
  const [generation, setGeneration] = useState<Generation<T> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  const refresh = useCallback(async () => {
    try { const value = await api.generation<T>(docId, kind); if (alive.current) { setGeneration(value); setError(""); } }
    catch (e) { if (alive.current) setError((e as Error).message); }
  }, [docId, kind]);
  useEffect(() => { alive.current = true; void refresh(); return () => { alive.current = false; }; }, [refresh]);
  const running = generation?.status === "running" || generation?.status === "queued";
  useEffect(() => { if (!running) return; const timer = setInterval(() => void refresh(), 2000); return () => clearInterval(timer); }, [running, refresh]);
  async function start(options: GenerateOptions = {}) {
    setBusy(true); setError("");
    try { const value = await api.generate<T>(docId, kind, options); if (alive.current) setGeneration(value); }
    catch (e) { if (alive.current) setError((e as Error).message); }
    finally { if (alive.current) setBusy(false); }
  }
  async function cancel() {
    if (!generation) return;
    setBusy(true);
    try { await api.cancel(generation.id); await refresh(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return { generation, running, busy, error, start, cancel, refresh };
}
