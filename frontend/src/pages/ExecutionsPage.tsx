import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import type { SessionListResponse, SessionSummary } from "../api/types";
import { SessionStatusBadge } from "../components/SessionStatusBadge";

const POLL_INTERVAL_MS = 4000;

function isActive(status: SessionSummary["status"]): boolean {
  return status === "queued" || status === "running";
}

export default function ExecutionsPage() {
  const [items, setItems] = useState<SessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const data = await apiClient.get<SessionListResponse>("/api/sessions?limit=50&offset=0");
      setItems(data.items);
      setTotal(data.total);
      setError(null);
    } catch {
      setError("Failed to load executions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    if (!items.some((session) => isActive(session.status))) return;
    const id = setInterval(fetchSessions, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [items, fetchSessions]);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Executions</h1>
        <Link to="/upload" className="button-link">
          New scrape
        </Link>
      </div>

      {loading && <p>Loading executions…</p>}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}

      {!loading && !error && items.length === 0 && (
        <p className="empty-state">No scrape sessions yet.</p>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Source</th>
                <th>Created</th>
                <th>Started</th>
                <th>Finished</th>
                <th>OK count</th>
              </tr>
            </thead>
            <tbody>
              {items.map((session) => (
                <tr key={session.id}>
                  <td>
                    <Link to={`/executions/${session.id}`} className="mono">
                      {session.id}
                    </Link>
                  </td>
                  <td>
                    <SessionStatusBadge status={session.status} />
                  </td>
                  <td>{session.source}</td>
                  <td>{session.created_at}</td>
                  <td>{session.started_at ?? "—"}</td>
                  <td>{session.finished_at ?? "—"}</td>
                  <td>{session.ok_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="table-total">
            {items.length} of {total} sessions
          </p>
        </div>
      )}
    </div>
  );
}
