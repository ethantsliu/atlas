import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const THEME_KEY = "atlas-theme";

function readTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "dark" ? "#0c100d" : "#f8f5ef");
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => readTheme() ?? systemTheme());

  useEffect(() => applyTheme(theme), [theme]);

  useEffect(() => {
    if (readTheme()) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const syncTheme = () => setTheme(media.matches ? "dark" : "light");
    media.addEventListener("change", syncTheme);
    return () => media.removeEventListener("change", syncTheme);
  }, []);

  const toggleTheme = () => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(THEME_KEY, next);
      } catch {
        // The active page still changes when storage is unavailable.
      }
      return next;
    });
  };

  return { theme, toggleTheme };
}
