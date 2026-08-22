import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { apiClient, setUnauthorizedHandler } from "../api/client";
import type { LoginResponse, LogoutResponse, MeResponse } from "../api/types";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  username: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setStatus("unauthenticated");
      setUsername(null);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<MeResponse>("/api/auth/me", { skipAuthRedirect: true })
      .then((data) => {
        if (cancelled) return;
        if (data.authenticated) {
          setStatus("authenticated");
          setUsername(data.username);
        } else {
          setStatus("unauthenticated");
          setUsername(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("unauthenticated");
          setUsername(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      username,
      async login(user: string, password: string) {
        await apiClient.post<LoginResponse>(
          "/api/auth/login",
          { username: user, password },
          { skipAuthRedirect: true },
        );
        setStatus("authenticated");
        setUsername(user);
      },
      async logout() {
        try {
          await apiClient.post<LogoutResponse>("/api/auth/logout", undefined, {
            skipAuthRedirect: true,
          });
        } finally {
          setStatus("unauthenticated");
          setUsername(null);
        }
      },
    }),
    [status, username],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- hook lives alongside its provider by design
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
