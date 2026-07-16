/** Render integer minor units as a human amount. Never used for arithmetic. */
export function formatMinor(amountMinor: number, currency: string): string {
  const major = Math.trunc(Math.abs(amountMinor) / 100);
  const minor = Math.abs(amountMinor) % 100;
  const sign = amountMinor < 0 ? "-" : "";
  return `${sign}${major},${String(minor).padStart(2, "0")} ${currency}`;
}
