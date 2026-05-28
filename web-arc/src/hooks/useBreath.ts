import { useEffect, useState } from "react";

// A small "breathing" number in [-amp, +amp] used to pulse status badges,
// alert pills and similar.
export function useBreath(seed = 1, period = 1000, amp = 1): number {
  const [v, setV] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setV(Math.sin(Date.now() / 400 + seed) * amp), period);
    return () => clearInterval(t);
  }, [seed, period, amp]);
  return v;
}
