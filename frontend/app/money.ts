export const currencies = [
  "USD",
  "EUR",
  "GBP",
  "BDT",
  "INR",
  "JPY",
  "CAD",
  "AUD",
];
export function currencyFactor(currency: string): number {
  try {
    const digits =
      new Intl.NumberFormat("en", {
        style: "currency",
        currency,
      }).resolvedOptions().maximumFractionDigits ?? 2;
    return 10 ** digits;
  } catch {
    return 100;
  }
}
export function displayMoney(amountMinor: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
    }).format(amountMinor / currencyFactor(currency));
  } catch {
    return `${currency} ${amountMinor / currencyFactor(currency)}`;
  }
}
