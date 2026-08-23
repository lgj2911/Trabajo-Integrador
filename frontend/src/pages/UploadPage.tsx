import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, ApiError } from "../api/client";
import type { SessionSummary, SessionSource } from "../api/types";
import { UploadDropzone } from "../components/UploadDropzone";

export default function UploadPage() {
  const [mode, setMode] = useState<SessionSource>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [concurrency, setConcurrency] = useState("5");
  const [delay, setDelay] = useState("0.5");
  const [resumeManifest, setResumeManifest] = useState<File | null>(null);
  const [resumeCheckpoint, setResumeCheckpoint] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (mode === "upload" && !file) {
      setError("Please select a .zip file containing the Rosario CSV files.");
      return;
    }

    const form = new FormData();
    form.set("source", mode);
    if (mode === "upload" && file) {
      form.set("file", file);
    }
    if (concurrency.trim() !== "") form.set("concurrency", concurrency.trim());
    if (delay.trim() !== "") form.set("delay", delay.trim());
    if (resumeManifest) form.set("resume_manifest", resumeManifest);
    if (resumeCheckpoint) form.set("resume_checkpoint", resumeCheckpoint);

    setSubmitting(true);
    try {
      const session = await apiClient.postForm<SessionSummary>("/api/sessions", form);
      navigate(`/executions/${session.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail ?? "Failed to start the scrape session.");
      } else {
        setError("Failed to reach the server. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <h1>Start a new scrape</h1>

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "upload"}
          className={mode === "upload" ? "tab active" : "tab"}
          onClick={() => setMode("upload")}
        >
          Upload ZIP
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "portal"}
          className={mode === "portal" ? "tab active" : "tab"}
          onClick={() => setMode("portal")}
        >
          Fetch from Rosario Open Data
        </button>
      </div>

      <form className="upload-form" onSubmit={handleSubmit}>
        {mode === "upload" ? (
          <UploadDropzone
            file={file}
            onSelect={(f) => setFile(f)}
            onClear={() => setFile(null)}
          />
        ) : (
          <p className="upload-hint">
            The backend will fetch the current Rosario CSV datasets directly from the open-data
            portal — no file needed.
          </p>
        )}

        <div className="form-row">
          <label htmlFor="concurrency">Concurrency</label>
          <input
            id="concurrency"
            type="number"
            min={1}
            max={20}
            value={concurrency}
            onChange={(e) => setConcurrency(e.target.value)}
          />
        </div>

        <div className="form-row">
          <label htmlFor="delay">Delay between requests (seconds)</label>
          <input
            id="delay"
            type="number"
            min={0}
            step={0.1}
            value={delay}
            onChange={(e) => setDelay(e.target.value)}
          />
        </div>

        <fieldset className="resume-fieldset">
          <legend>Resume from a previous export (optional)</legend>
          <p className="upload-hint">
            Already have a corpus from a prior run? Upload its <code>manifest.csv</code>
            and/or <code>checkpoint.json</code> so this scrape skips documents you already
            have instead of re-downloading them.
          </p>

          <div className="form-row">
            <label htmlFor="resume-manifest">manifest.csv</label>
            <input
              id="resume-manifest"
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setResumeManifest(e.target.files?.[0] ?? null)}
            />
          </div>

          <div className="form-row">
            <label htmlFor="resume-checkpoint">checkpoint.json</label>
            <input
              id="resume-checkpoint"
              type="file"
              accept=".json,application/json"
              onChange={(e) => setResumeCheckpoint(e.target.files?.[0] ?? null)}
            />
          </div>
        </fieldset>

        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}

        <button type="submit" disabled={submitting}>
          {submitting
            ? "Starting…"
            : mode === "upload"
              ? "Upload and start scrape"
              : "Fetch from portal and start scrape"}
        </button>
      </form>
    </div>
  );
}
