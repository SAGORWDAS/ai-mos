"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
type Entry = {
  id: string;
  created_at: number;
  status: string;
  draft_id: string;
  result: { simulated?: boolean; error?: string };
};
type Digest = { since: number; items: Entry[]; next_offset: number | null };
export default function ReplyDigest({ brand }: { brand: string }) {
  const [data, setData] = useState<Digest | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    if (brand)
      api<Digest>(`/v1/brands/${brand}/reply-digest`)
        .then((r) => {
          if (active) setData(r);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [brand]);
  async function load(more = false) {
    setBusy(true);
    setError("");
    try {
      const row = await api<Digest>(
        `/v1/brands/${brand}/reply-digest?offset=${more ? data?.next_offset || 0 : 0}`,
      );
      setData((current) => ({
        ...row,
        items: more ? [...(current?.items || []), ...row.items] : row.items,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load digest.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <h4>Automatic reply digest · last seven days</h4>
      <p className="small muted">
        All automatic reply effects are recorded, including queued, failed and
        uncertain delivery. Sandbox entries are labelled. Refresh to see new
        activity; this digest does not send email.
      </p>
      <button disabled={!brand || busy} onClick={() => load()}>
        Refresh reply digest
      </button>
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Created</th>
                  <th>Delivery</th>
                  <th>Effect / draft</th>
                  <th>Mode / issue</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id}>
                    <td>{new Date(e.created_at * 1000).toLocaleString()}</td>
                    <td>{e.status}</td>
                    <td>
                      {e.id}
                      <br />
                      {e.draft_id}
                    </td>
                    <td>
                      {e.result.simulated ? "Sandbox" : "Connected"}
                      {e.result.error ? ` · ${e.result.error}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data.items.length && (
            <p>No automatic reply effects in the last seven days.</p>
          )}
          {data.next_offset !== null && (
            <button disabled={busy} onClick={() => load(true)}>
              Load more replies
            </button>
          )}
        </>
      )}
    </section>
  );
}
