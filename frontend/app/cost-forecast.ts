export type ForecastInput = {
  prospects: number;
  variablePer100: number[];
  fixedMonthly: number;
  rates: number[];
  firstYearRevenue: number;
};

export function costForecast(input: ForecastInput) {
  const values = [
    input.prospects,
    ...input.variablePer100,
    input.fixedMonthly,
    ...input.rates,
    input.firstYearRevenue,
  ];
  if (
    values.some((v) => !Number.isFinite(v) || v < 0 || v > 1e9) ||
    input.rates.length !== 5 ||
    input.rates.some((v) => v > 100)
  )
    throw new Error("Use nonnegative numbers and rates between 0 and 100.");
  const variableCost =
    (input.variablePer100.reduce((sum, v) => sum + v, 0) * input.prospects) /
    100;
  const total = variableCost + input.fixedMonthly;
  const counts = input.rates.reduce<number[]>(
    (counts, rate) => [
      ...counts,
      ((counts.at(-1) ?? input.prospects) * rate) / 100,
    ],
    [],
  );
  const per = (count: number) => (count > 0 ? total / count : null);
  return {
    variableCost,
    total,
    counts,
    cpl: per(counts[0]),
    costPerReply: per(counts[2]),
    cac: per(counts[4]),
    expectedRevenue: counts[4] * input.firstYearRevenue,
  };
}
