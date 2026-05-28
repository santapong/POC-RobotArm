import { useEffect, useState } from "react";

// Re-renders every second with the current Date — drives the UTC clock in
// the top bar.
export function useClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}
