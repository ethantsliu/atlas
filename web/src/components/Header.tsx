import { useEffect, useRef } from "react";
import { Asterisk, Moon, Search, Sun } from "lucide-react";
import type { Theme } from "../hooks/theme";
import { labelOf } from "../lib/text";

export const APP_VIEWS = [
  "map",
  "daily",
  "insights",
  "library",
  "briefs",
  "coverage",
] as const;

export type AppView = (typeof APP_VIEWS)[number];

type AppHeaderProps = {
  view: AppView;
  query: string;
  theme: Theme;
  onViewChange: (view: AppView) => void;
  onQueryChange: (query: string) => void;
  onThemeChange: () => void;
};

export function AppHeader({
  view,
  query,
  theme,
  onViewChange,
  onQueryChange,
  onThemeChange,
}: AppHeaderProps) {
  const searchRef = useRef<HTMLInputElement>(null);
  const isDark = theme === "dark";

  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (document.querySelector('[aria-modal="true"]')) return;
        searchRef.current?.focus();
      }
    }
    document.addEventListener("keydown", focusSearch);
    return () => document.removeEventListener("keydown", focusSearch);
  }, []);

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">
          <Asterisk size={21} />
        </div>
        <div className="brand-copy">
          <strong>Atlas</strong>
          <span>A field guide to testable research</span>
        </div>
        <button
          className="theme-toggle"
          type="button"
          onClick={onThemeChange}
          aria-label={isDark ? "Use light mode" : "Use dark mode"}
          aria-pressed={isDark}
          title={isDark ? "Use light mode" : "Use dark mode"}
        >
          {isDark ? <Sun size={17} /> : <Moon size={17} />}
        </button>
      </div>

      <nav aria-label="Atlas views">
        {APP_VIEWS.map((item) => (
          <button
            className={view === item ? "active" : ""}
            onClick={() => onViewChange(item)}
            aria-current={view === item ? "page" : undefined}
            key={item}
          >
            {labelOf(item)}
          </button>
        ))}
      </nav>

      <label className="search">
        <Search size={16} />
        <input
          ref={searchRef}
          value={query}
          onChange={(event) => {
            if (view === "insights" || view === "coverage") onViewChange("map");
            onQueryChange(event.target.value);
          }}
          placeholder={
            view === "daily"
              ? "Search today’s papers…"
              : "Search concepts, papers, ideas…"
          }
          aria-label="Search the atlas"
        />
        <kbd>⌘/Ctrl K</kbd>
      </label>
    </header>
  );
}
