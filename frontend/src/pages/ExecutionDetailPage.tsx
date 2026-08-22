import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import type { SessionDetail } from "../api/types";
import { SessionStatusBadge } from "../components/SessionStatusBadge";
import { LogViewer } from "../components/LogViewer";

const TERMINAL_STATUSES: SessionDetail["status"][] = ["completed", "failed", "interrupted"];
const POLL_INTERVAL_MS = 5000;

export default function ExecutionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const data = await apiClient.get<SessionDetail>(`/api/sessions/${id}`);
      setDetail(data);
      setNotFound(false);
    } catch {
      setNotFound(true);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!detail || TERMINAL_STATUSES.includes(detail.status)) return;
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [detail, load]);

  async function handleDownload() {
    if (!id) return;
    setDownloadError(null);
    setDownloading(true);
    try {
      const blob = await apiClient.getBlob(`/api/sessions/${id}/download`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `session-${id}.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadError("Download is not available yet. The session may not have finished.");
    } finally {
      setDownloading(false);
    }
  }

  if (!id) return null;

  if (notFound) {
    return (
      <div className="page">
        <p role="alert">Session not found.</p>
      </div>
    );
  }

  const isTerminal = detail ? TERMINAL_STATUSES.includes(detail.status) : false;

  return (
    <div className="page">
      <div className="page-header">
        <h1>
          Execution <span className="mono">{id}</span>
        </h1>
        {detail && <SessionStatusBadge status={detail.status} />}
      </div>

      {!detail && <p>Loading session details…</p>}

      {detail && (
        <>
          <dl className="detail-grid">
            <dt>Source</dt>
            <dd>{detail.source}</dd>
            <dt>Created</dt>
            <dd>{detail.created_at}</dd>
            <dt>Started</dt>
            <dd>{detail.started_at ?? "—"}</dd>
            <dt>Finished</dt>
            <dd>{detail.finished_at ?? "—"}</dd>
            <dt>Concurrency</dt>
            <dd>{detail.concurrency}</dd>
            <dt>Delay</dt>
            <dd>{detail.delay}</dd>
            <dt>OK count</dt>
            <dd>{detail.ok_count}</dd>
            <dt>Output size</dt>
            <dd>{detail.output_size_bytes ?? "—"}</dd>
            <dt>CSV files</dt>
            <dd>
              {detail.csv_files_provided.length > 0 ? detail.csv_files_provided.join(", ") : "—"}
            </dd>
            {detail.error_message && (
              <>
                <dt>Error</dt>
                <dd role="alert">{detail.error_message}</dd>
              </>
            )}
          </dl>

          <div className="actions-row">
            <button type="button" onClick={handleDownload} disabled={!isTerminal || downloading}>
              {downloading ? "Preparing download…" : "Download results"}
            </button>
            <Link to={`/files?session_id=${id}`}>View files for this session</Link>
          </div>

          {downloadError && (
            <p role="alert" className="form-error">
              {downloadError}
            </p>
          )}

          <h2>Logs</h2>
          <LogViewer sessionId={id} />
        </>
      )}
    </div>
  );
}
