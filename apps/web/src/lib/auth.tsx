"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { fetchMe } from "./api";
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
    let cancelled = false;
    const tok = localStorage.getItem(TOKEN_KEY) || "";
    try {
      const raw = localStorage.getItem(USER_KEY);
      if (raw) setUser(JSON.parse(raw) as User);
    } catch {
      /* ignore */
    }
    setToken(tok);
    if (!tok) {
      setUser(null);
      return;
    }
    fetchMe()
      .then((fresh) => {
        if (cancelled) return;
        localStorage.setItem(USER_KEY, JSON.stringify(fresh));
        setUser(fresh);
        setToken(localStorage.getItem(TOKEN_KEY) || tok);
      })
      .catch(() => {
        if (cancelled) return;
        if (!localStorage.getItem(TOKEN_KEY)) {
          setUser(null);
          setToken("");
        }
      });
    return () => {
      cancelled = true;
    };
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
