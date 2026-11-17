export function credentialPayload(
  provider: string,
  values: Record<string, string>,
) {
  const credentials = Object.fromEntries(
    Object.entries(values).filter(([, value]) => value.trim() !== ""),
  );
  if (provider === "brave" && credentials.search_price_micros !== undefined) {
    const dollars = Number(credentials.search_price_micros);
    const units = Math.round(dollars * 1000000);
    if (
      !Number.isFinite(dollars) ||
      dollars < 0 ||
      dollars > 1000 ||
      (dollars > 0 && dollars < 0.000001) ||
      Math.abs(dollars * 1000000 - units) > 0.000001
    )
      throw new Error(
        "Enter a search price between $0 and $1,000, with at most six decimal places.",
      );
    credentials.search_price_micros = String(units);
  }
  return credentials;
}
