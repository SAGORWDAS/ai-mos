"use client";

import { useState } from "react";
import { costForecast } from "./cost-forecast";

const costLabels = [
  "Prospect data per 100",
  "Email verification per 100",
  "Sending costs per 100",
  "AI inference per 100",
  "Review time cost per 100",
];
const rateLabels = [
  "Discovered → qualified %",
  "Qualified → delivered %",
  "Delivered → reply %",
  "Reply → meeting %",
  "Meeting → customer %",
];
export default function CostPlanner() {
  const [volume, setVolume] = useState("100");
  const [costs, setCosts] = useState<string[]>(costLabels.map(() => ""));
  const [rates, setRates] = useState<string[]>(rateLabels.map(() => ""));
  const [fixed, setFixed] = useState("");
  const [revenue, setRevenue] = useState("");
  const complete = [volume, ...costs, ...rates, fixed, revenue].every(
    (v) => v.trim() !== "",
  );
  let forecast = null;
  let error = "";
  if (complete)
    try {
      forecast = costForecast({
        prospects: Number(volume),
        variablePer100: costs.map(Number),
        fixedMonthly: Number(fixed),
        rates: rates.map(Number),
        firstYearRevenue: Number(revenue),
      });
    } catch (e) {
      error = e instanceof Error ? e.message : "Invalid assumptions.";
    }
  const dollars = (value: number | null) =>
    value === null
      ? "No projected outcomes"
      : new Intl.NumberFormat(undefined, {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 2,
        }).format(value);
  return (
    <section className="operation-card">
      <h3>Campaign cost planner</h3>
      <p>
        Compare a monthly campaign before spending. Enter your own prices and
        funnel assumptions in USD; enter zero where a cost does not apply. This
        worksheet estimates results and does not change budgets or the expense
        ledger. Values stay on this screen and reset when you leave.
      </p>
      <div className="form-grid">
        <label>
          Monthly prospects
          <input
            type="number"
            min="0"
            max="1000000000"
            value={volume}
            onChange={(e) => setVolume(e.target.value)}
          />
        </label>
        {costLabels.map((label, i) => (
          <label key={label}>
            {label}
            <input
              type="number"
              min="0"
              step="0.01"
              value={costs[i]}
              onChange={(e) =>
                setCosts(costs.map((v, j) => (j === i ? e.target.value : v)))
              }
            />
          </label>
        ))}
        <label>
          Fixed monthly infrastructure
          <input
            type="number"
            min="0"
            step="0.01"
            value={fixed}
            onChange={(e) => setFixed(e.target.value)}
          />
        </label>
        <label>
          First-year revenue per customer
          <input
            type="number"
            min="0"
            step="0.01"
            value={revenue}
            onChange={(e) => setRevenue(e.target.value)}
          />
        </label>
        {rateLabels.map((label, i) => (
          <label key={label}>
            {label}
            <input
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={rates[i]}
              onChange={(e) =>
                setRates(rates.map((v, j) => (j === i ? e.target.value : v)))
              }
            />
          </label>
        ))}
      </div>
      {error && (
        <p role="alert" className="message error">
          {error}
        </p>
      )}
      {forecast ? (
        <div aria-live="polite">
          <p>
            <strong>Projected monthly cost: {dollars(forecast.total)}</strong> ·
            variable {dollars(forecast.variableCost)}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Expected count</th>
                </tr>
              </thead>
              <tbody>
                {[
                  "Qualified leads",
                  "Delivered messages",
                  "Replies",
                  "Meetings",
                  "Customers",
                ].map((label, i) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td>{forecast.counts[i].toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            Cost per qualified lead: {dollars(forecast.cpl)} · cost per reply:{" "}
            {dollars(forecast.costPerReply)} · acquisition cost:{" "}
            {dollars(forecast.cac)}
          </p>
          <p>
            Expected first-year revenue from this cohort:{" "}
            {dollars(forecast.expectedRevenue)}. Revenue excludes delivery
            costs, tax, churn and refunds.
          </p>
          <p className="small muted">
            Fractional outcomes are expectations, not promised clients. Use
            recorded Attribution results to replace these assumptions after a
            campaign.
          </p>
        </div>
      ) : (
        <p className="small muted">
          Fill every assumption to see a forecast. No provider prices or
          conversion rates are invented.
        </p>
      )}
    </section>
  );
}
