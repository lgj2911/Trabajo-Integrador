import { useEffect, useRef, useState } from "react";
import { apiUrl } from "../api/client";
import type { LogEndEvent, LogLineEvent } from "../api/types";

interface LogViewerProps {
  sessionId: string;
}

interface DisplayLine extends LogLineEvent {
  key: number;
}

/**
 * Auto-scrolling log pane that consumes the SSE stream at
 * GET /api/sessions/{id}/logs via a plain EventSource.
 *
 * Per the API contract, EventSource does not send cookies cross-origin by
 * default, so it must be constructed with { withCredentials: true }.
 */
export function LogViewer({ sessionId }: LogViewerProps) {
  const [lines, setLines] = useState<DisplayLine[]>([]);
  const [endStatus, setEndStatus] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const nextKey = useRef(0);

  useEffect(() => {
    setLines([]);
    setEndStatus(null);
    setConnectionError(false);
    nextKey.current = 0;

    const source = new EventSource(apiUrl(`/api/sessions/${sessionId}/logs`), {
      withCredentials: true,
    });

    source.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as LogLineEvent;
        setLines((prev) => [...prev, { ...data, key: nextKey.current++ }]);
      } catch {
        // Ignore malformed log lines rather than crashing the viewer.
      }
    };

    source.addEventListener("end", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent<string>).data) as LogEndEvent;
        setEndStatus(data.status);
      } catch {
        setEndStatus("unknown");
      }
      source.close();
    });

    source.onerror = () => {
      setConnectionError(true);
    };

    return () => source.close();
  }, [sessionId]);

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div className="log-viewer" ref={containerRef} data-testid="log-viewer">
      {lines.length === 0 && !connectionError && (
        <p className="log-viewer-empty">Waiting for log output…</p>
      )}
      {lines.map((l) => (
        <div className="log-line" key={l.key}>
          <span className="log-ts">{l.ts}</span>
          <span className="log-text">{l.line}</span>
        </div>
      ))}
      {endStatus && (
        <div className="log-end" role="status">
          Log stream ended — final status: {endStatus}
        </div>
      )}
      {connectionError && !endStatus && (
        <div className="log-error" role="status">
          Connection to the log stream was interrupted. Reconnecting…
        </div>
      )}
    </div>
  );
}
