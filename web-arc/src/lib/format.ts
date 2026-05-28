// Time / number formatting helpers used by the top bar, logs, and HUDs.

export function utcHMS(d: Date): string {
  return [d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()]
    .map(n => String(n).padStart(2, "0")).join(":");
}

export function utcDate(d: Date): string {
  return [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()]
    .map(n => String(n).padStart(2, "0")).join("-");
}

export function pad(n: number, w: number): string {
  return String(n).padStart(w, "0");
}
