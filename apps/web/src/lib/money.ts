/**
 * Money on the wire is an exact decimal string ("3000.00"), never a number.
 *
 * JSON numbers are IEEE doubles, so parsing an amount into one is the float the
 * contract forbids: 0.1 + 0.2 is not 0.3, and a total assembled that way is
 * wrong in the last place in a way nobody notices until a reconciliation does.
 * So amounts arrive as strings and stay strings, and the only arithmetic here
 * is over integer minor units, which a double represents exactly well past any
 * amount a school will ever bill.
 *
 * Minor units exist only inside this module, for summing and subtracting. They
 * are never stored, sent, or treated as the amount itself.
 */

const MINOR_PER_MAJOR = 100;

/** Parse the wire format into exact integer minor units. */
export function toMinor(amount: string): number {
  const trimmed = amount.trim();
  const negative = trimmed.startsWith("-");
  const [major = "0", fraction = ""] = trimmed.replace(/^[-+]/, "").split(".");
  const minor = Number(major) * MINOR_PER_MAJOR + Number(fraction.padEnd(2, "0").slice(0, 2));
  return negative ? -minor : minor;
}

/** Render exact minor units back into the wire format. */
export function fromMinor(minor: number): string {
  const sign = minor < 0 ? "-" : "";
  const absolute = Math.abs(Math.trunc(minor));
  const major = Math.trunc(absolute / MINOR_PER_MAJOR);
  const fraction = absolute % MINOR_PER_MAJOR;
  return `${sign}${major}.${String(fraction).padStart(2, "0")}`;
}

/** Sum wire amounts exactly, returning minor units. */
export function sumMinor(amounts: string[]): number {
  return amounts.reduce((total, amount) => total + toMinor(amount), 0);
}

/** Display an amount from the wire, in the local convention. */
export function formatAmount(amount: string, currency: string): string {
  return `${fromMinor(toMinor(amount)).replace(".", ",")} ${currency}`;
}

/** Display an amount held as minor units (a computed subtotal). */
export function formatMinor(minor: number, currency: string): string {
  return `${fromMinor(minor).replace(".", ",")} ${currency}`;
}

/**
 * What a person typed into an amount field, as the wire format.
 *
 * Accepts a comma or a dot as the decimal separator, since the product's own
 * convention is a comma. An unparseable value becomes "0.00" rather than NaN,
 * so the request is refused by the server's validation instead of by a crash.
 */
export function amountFromInput(value: string): string {
  const normalised = value.trim().replace(",", ".");
  if (!/^-?\d*\.?\d*$/.test(normalised) || normalised === "" || normalised === "-") {
    return "0.00";
  }
  return fromMinor(toMinor(normalised));
}
