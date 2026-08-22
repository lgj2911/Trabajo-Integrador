import { useRef, useState } from "react";
import type { DragEvent, KeyboardEvent } from "react";

interface UploadDropzoneProps {
  file: File | null;
  onSelect: (file: File) => void;
  onClear: () => void;
}

function isZipFile(file: File): boolean {
  const nameOk = file.name.toLowerCase().endsWith(".zip");
  const zipMimeTypes = ["application/zip", "application/x-zip-compressed", "application/octet-stream", ""];
  return nameOk && zipMimeTypes.includes(file.type);
}

/** Drag-and-drop (or click-to-browse) zone that only accepts a single .zip file. */
export function UploadDropzone({ file, onSelect, onClear }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFiles(files: FileList | null) {
    const candidate = files?.[0];
    if (!candidate) return;
    if (!isZipFile(candidate)) {
      setError(`"${candidate.name}" is not a .zip file. Please choose a .zip archive.`);
      return;
    }
    setError(null);
    onSelect(candidate);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    handleFiles(event.dataTransfer.files);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <div className="dropzone-wrapper">
      <div
        className={`dropzone${dragOver ? " dropzone--active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-label="Upload a .zip file"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".zip,application/zip"
          hidden
          aria-label="file-input"
          onChange={(e) => handleFiles(e.target.files)}
        />
        {file ? (
          <div className="dropzone-file">
            <span>{file.name}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setError(null);
                onClear();
              }}
            >
              Remove
            </button>
          </div>
        ) : (
          <p>Drag and drop a .zip file here, or click to browse.</p>
        )}
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
    </div>
  );
}
