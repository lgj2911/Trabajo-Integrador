import type { SessionStatus } from "../api/types";

const LABELS: Record<SessionStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  interrupted: "Interrupted",
  cancelled: "Cancelled",
};

export function SessionStatusBadge({ status }: { status: SessionStatus }) {
  return <span className={`status-badge status-badge--${status}`}>{LABELS[status]}</span>;
}
