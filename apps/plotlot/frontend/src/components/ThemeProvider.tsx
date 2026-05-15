"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  resolved: Theme;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  resolved: "light",
  setTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

function resolveInitialTheme(): Theme {
  return "light";
}

function applyThemeClass(theme: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Keep the first render deterministic (matches server HTML); reconcile in an effect.
  const [theme, setThemeState] = useState<Theme>("light");

  useEffect(() => {
    const initial = resolveInitialTheme();
    applyThemeClass(initial);
    const frame = window.requestAnimationFrame(() => {
      setThemeState(initial);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const setTheme = useCallback(() => {
    setThemeState("light");
    applyThemeClass("light");
    try {
      localStorage.setItem("theme", "light");
    } catch {
      // ignore storage errors
    }
  }, []);

  const value = useMemo<ThemeContextValue>(() => {
    return { theme, resolved: theme, setTheme };
  }, [setTheme, theme]);

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}
