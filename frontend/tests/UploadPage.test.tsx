import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import UploadPage from "../src/pages/UploadPage";
import { apiClient } from "../src/api/client";
import type { SessionSummary } from "../src/api/types";

vi.mock("../src/api/client", async () => {
  const actual = await vi.importActual<typeof import("../src/api/client")>("../src/api/client");
  return {
    ...actual,
    apiClient: {
      get: vi.fn(),
      post: vi.fn(),
      postForm: vi.fn(),
      getBlob: vi.fn(),
    },
  };
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/upload"]}>
      <Routes>
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/executions/:id" element={<div>Execution detail page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const sampleSession: SessionSummary = {
  id: "abc123",
  status: "queued",
  source: "upload",
  created_at: "2026-01-01T00:00:00Z",
  started_at: null,
  finished_at: null,
  ok_count: 0,
  error_message: null,
};

describe("UploadPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("rejects a non-zip file before it can be submitted", async () => {
    renderPage();

    const input = screen.getByLabelText(/file-input/i);
    const textFile = new File(["hello"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [textFile] } });

    expect(await screen.findByRole("alert")).toHaveTextContent(/not a \.zip file/i);
    expect(apiClient.postForm).not.toHaveBeenCalled();
  });

  it("submits a valid zip upload and navigates to the new session detail page", async () => {
    vi.mocked(apiClient.postForm).mockResolvedValue(sampleSession);
    const user = userEvent.setup();
    renderPage();

    const input = screen.getByLabelText(/file-input/i);
    const zipFile = new File(["zipcontent"], "data.zip", { type: "application/zip" });
    fireEvent.change(input, { target: { files: [zipFile] } });

    await user.click(screen.getByRole("button", { name: /upload and start scrape/i }));

    expect(await screen.findByText(/execution detail page/i)).toBeInTheDocument();
    expect(apiClient.postForm).toHaveBeenCalledWith("/api/sessions", expect.any(FormData));
  });

  it("submits the portal mode without requiring a file", async () => {
    vi.mocked(apiClient.postForm).mockResolvedValue({ ...sampleSession, source: "portal" });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: /fetch from rosario open data/i }));
    await user.click(screen.getByRole("button", { name: /fetch from portal and start scrape/i }));

    expect(await screen.findByText(/execution detail page/i)).toBeInTheDocument();
  });
});
