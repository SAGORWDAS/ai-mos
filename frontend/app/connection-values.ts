export function credentialPayload(
  provider: string,
  values: Record<string, string>,
) {
  const credentials = Object.fromEntries(
    Object.entries(values).filter(([, value]) => value.trim() !== ""),
  );
  const field =
    provider === "brave"
      ? "search_price_micros"
      : provider === "openrouter"
        ? "max_cost_micros"
        : null;
  const maximum = provider === "brave" ? 1000 : 1;
  if (field && credentials[field] !== undefined) {
    const dollars = Number(credentials[field]);
    const units = Math.round(dollars * 1000000);
    if (
      !Number.isFinite(dollars) ||
      dollars < 0 ||
      dollars > maximum ||
      (dollars > 0 && dollars < 0.000001) ||
      Math.abs(dollars * 1000000 - units) > 0.000001
    )
      throw new Error(
        `Enter a USD amount between $0 and $${maximum.toLocaleString()}, with at most six decimal places.`,
      );
    credentials[field] = String(units);
  }
  return credentials;
}
