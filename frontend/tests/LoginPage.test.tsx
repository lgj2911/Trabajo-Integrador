import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../src/auth/AuthContext";
import LoginPage from "../src/pages/LoginPage";
import { apiClient, ApiError } from "../src/api/client";

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
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockResolvedValue({ authenticated: false, username: "" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders username and password fields", async () => {
    renderPage();
    expect(await screen.findByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("submits credentials and calls the login endpoint", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByLabelText(/username/i), "alice");
    await user.type(screen.getByLabelText(/password/i), "s3cret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/api/auth/login",
        { username: "alice", password: "s3cret" },
        { skipAuthRedirect: true },
      );
    });
  });

  it("shows an error message when login fails", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(
      new ApiError(401, "Unauthorized", "Invalid credentials"),
    );
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByLabelText(/username/i), "alice");
    await user.type(screen.getByLabelText(/password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid credentials/i);
  });
});
