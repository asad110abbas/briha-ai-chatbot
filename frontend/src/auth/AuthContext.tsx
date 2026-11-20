import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, post } from "../lib/api";
import type { Me } from "../lib/types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  signedOut: boolean; // true right after the user pressed "Log out" (not an expired session)
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [signedOut, setSignedOut] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUser(await api<Me>("/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onLoggedOut = () => setUser(null);
    window.addEventListener("briha:logged-out", onLoggedOut);
    return () => window.removeEventListener("briha:logged-out", onLoggedOut);
  }, [refresh]);

  const login = async (username: string, password: string) => {
    const { user } = await post<{ user: Me }>("/auth/login", { username, password });
    setUser(user);
    setSignedOut(false);
    return user;
  };

  const logout = async () => {
    await post("/auth/logout").catch(() => undefined);
    setSignedOut(true);
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, loading, login, logout, refresh, signedOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
