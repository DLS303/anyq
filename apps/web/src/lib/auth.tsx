"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { User } from "./types";

const USER_KEY = "superapp_user";
const TOKEN_KEY = "superapp_token";

type AuthState = {
  user: User | null;
  token: string;
  login: (user: User, token: string) => void;
  logout: () => void;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(USER_KEY);
      const tok = localStorage.getItem(TOKEN_KEY) || "";
      if (raw) setUser(JSON.parse(raw) as User);
      setToken(tok);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      token,
      login: (next, tok) => {
        localStorage.setItem(USER_KEY, JSON.stringify(next));
        localStorage.setItem(TOKEN_KEY, tok);
        setUser(next);
        setToken(tok);
      },
      logout: () => {
        localStorage.removeItem(USER_KEY);
        localStorage.removeItem(TOKEN_KEY);
        setUser(null);
        setToken("");
      },
    }),
    [user, token],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("AuthProvider missing");
  return ctx;
}
