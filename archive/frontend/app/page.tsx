export const dynamic = "force-dynamic";

type Health = { status: string; checks: Record<string, boolean> };

async function getHealth(): Promise<Health | { status: string; checks: {} }> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${base}/healthz`, { cache: "no-store" });
    return (await res.json()) as Health;
  } catch {
    return { status: "unreachable", checks: {} };
  }
}

export default async function Page() {
  const health = await getHealth();
  const rows = Object.entries(health.checks);

  return (
    <main
      style={{
        fontFamily: "Georgia, serif",
        maxWidth: 640,
        margin: "12vh auto",
        padding: "0 24px",
        lineHeight: 1.55,
        color: "#111",
      }}
    >
      <p style={{ fontFamily: "system-ui", fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#777" }}>
        AI-MOS · T-1.1
      </p>
      <h1 style={{ fontSize: 40, fontWeight: 400, margin: "8px 0 4px", letterSpacing: "-0.02em" }}>
        Stack status
      </h1>
      <p style={{ color: "#555", marginTop: 0 }}>
        API reports <strong>{health.status}</strong>.
      </p>

      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "system-ui", fontSize: 13, marginTop: 24 }}>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td style={{ padding: "8px 0", borderTop: "1px solid #000" }}>No checks returned</td>
            </tr>
          ) : (
            rows.map(([name, ok]) => (
              <tr key={name}>
                <td style={{ padding: "8px 0", borderTop: "1px solid #000" }}>{name}</td>
                <td style={{ padding: "8px 0", borderTop: "1px solid #000", textAlign: "right" }}>
                  {ok ? "reachable" : "unreachable"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <p style={{ fontFamily: "system-ui", fontSize: 11, color: "#888", marginTop: 32 }}>
        Placeholder screen. The real navigation arrives in PH-2.
      </p>
    </main>
  );
}
