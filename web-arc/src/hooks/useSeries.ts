import { useEffect, useState } from "react";

// Deterministic seeded RNG so each spark chart starts identical across runs.
function rng(seed: number): () => number {
  let s = seed;
  return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
}

// Rolling time-series buffer for sparklines — pushes a new sample every
// ~800 ms and drops the oldest, keeping `len` values.
export function useSeries(seed: number, len = 60, base = 50, swing = 25): number[] {
  const [series, setSeries] = useState<number[]>(() => {
    const r = rng(seed);
    return Array.from({ length: len }, () => base + (r() - 0.5) * swing);
  });
  useEffect(() => {
    const t = setInterval(() => {
      setSeries((s) => {
        const last = s[s.length - 1];
        const next = Math.max(0, Math.min(100, last + (Math.random() - 0.5) * (swing / 4)));
        return [...s.slice(1), next];
      });
    }, 800);
    return () => clearInterval(t);
  }, [swing]);
  return series;
}
