import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { FILE_CATEGORIES } from "../api/types";
import type { FileEntry, FileListResponse } from "../api/types";
import { FileTable } from "../components/FileTable";
import { Pagination } from "../components/Pagination";

const PAGE_SIZE = 100;

export default function FilesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const category = searchParams.get("category") ?? "";
  const source = searchParams.get("source") ?? "";
  const sessionId = searchParams.get("session_id") ?? "";
  const q = searchParams.get("q") ?? "";
  const offset = Number(searchParams.get("offset") ?? "0");

  const [items, setItems] = useState<FileEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (source) params.set("source", source);
    if (sessionId) params.set("session_id", sessionId);
    if (q) params.set("q", q);
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(offset));

    apiClient
      .get<FileListResponse>(`/api/files?${params.toString()}`)
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
        setError(null);
      })
      .catch(() => {
        if (!cancelled) setError("Failed to load files.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [category, source, sessionId, q, offset]);

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    // Any filter change invalidates the current page -- start back at the top.
    if (key !== "offset") {
      next.delete("offset");
    }
    setSearchParams(next);
  }

  return (
    <div className="page">
      <h1>Scraped files</h1>

      <div className="filters-row">
        <label>
          Category
          <select
            value={category}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => updateParam("category", e.target.value)}
          >
            <option value="">All categories</option>
            {FILE_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>

        <label>
          Source
          <input
            value={source}
            onChange={(e) => updateParam("source", e.target.value)}
            placeholder="rosario / santafe"
          />
        </label>

        <label>
          Filename search
          <input
            value={q}
            onChange={(e) => updateParam("q", e.target.value)}
            placeholder="Search filename…"
          />
        </label>

        {sessionId && (
          <div className="session-filter-chip">
            Session: <span className="mono">{sessionId}</span>
            <button type="button" onClick={() => updateParam("session_id", "")}>
              Clear
            </button>
          </div>
        )}
      </div>

      {loading && <p>Loading files…</p>}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}

      {!loading && !error && (
        <>
          <FileTable items={items} />
          <Pagination
            total={total}
            limit={PAGE_SIZE}
            offset={offset}
            onOffsetChange={(next) => updateParam("offset", String(next))}
            itemLabel="files"
          />
        </>
      )}
    </div>
  );
}
