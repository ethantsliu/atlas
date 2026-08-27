import { Suspense, useEffect } from "react";
import { Sparkles } from "lucide-react";
import { AppHeader, type AppView } from "./components/Header";
import { ViewLoader } from "./components/Loader";
import { useAtlas } from "./hooks/atlas";
import { useTheme } from "./hooks/theme";
import { useAtlasUrl } from "./hooks/url";
import { ALL_NODE_KINDS } from "./lib/graph";
import {
  BriefsView,
  CoverageView,
  DailyView,
  InsightsView,
  LibraryView,
  MapView,
} from "./views/Load";

const PAPER_VIEWS = new Set<AppView>(["insights", "library", "briefs", "coverage"]);

export default function App() {
  const load = useAtlas();
  const { theme, toggleTheme } = useTheme();
  const { state, replace, push, shareUrl } = useAtlasUrl();
  const needsPapers =
    PAPER_VIEWS.has(state.view) ||
    (state.view === "map" &&
      (state.kinds.includes("paper") ||
        state.kinds.includes("idea") ||
        Boolean(state.selected) ||
        state.query.trim().length > 0 ||
        state.focus?.startsWith("paper-")));

  useEffect(() => {
    if (
      load.core &&
      needsPapers &&
      !load.papersReady &&
      !load.papersLoading &&
      !load.papersError
    ) {
      load.loadPapers();
    }
  }, [
    load.core,
    load.loadPapers,
    load.papersError,
    load.papersLoading,
    load.papersReady,
    needsPapers,
  ]);

  if (load.error) {
    return (
      <div className="loading" role="alert" aria-atomic="true">
        <Sparkles />
        <span>Unable to build the atlas: {load.error}</span>
        <button type="button" onClick={load.retry}>
          Try again
        </button>
      </div>
    );
  }

  const mapAtlas = load.atlas ?? load.preview;
  if (!mapAtlas) {
    return (
      <div
        className="loading"
        role="status"
        aria-live="polite"
        aria-atomic="true"
        aria-busy="true"
      >
        <Sparkles /> Building the atlas…
      </div>
    );
  }

  const paperFallback = load.papersError ? (
    <main className="loading" role="alert" aria-atomic="true">
      <span>Unable to load the paper index: {load.papersError}</span>
      <button type="button" onClick={load.retryPapers}>
        Retry papers
      </button>
    </main>
  ) : (
    <ViewLoader view={state.view} />
  );

  return (
    <div className="app-shell">
      <AppHeader
        view={state.view}
        query={state.query}
        theme={theme}
        onViewChange={(view) => push({ view })}
        onQueryChange={(query) => replace({ query })}
        onThemeChange={toggleTheme}
      />

      <Suspense fallback={<ViewLoader view={state.view} />}>
        {state.view === "map" && (
          <MapView
            atlas={mapAtlas}
            theme={theme}
            url={state}
            shareUrl={shareUrl}
            papersReady={load.papersReady}
            papersLoading={load.papersLoading}
            papersError={load.papersError}
            onNeedPapers={load.loadPapers}
            onRetryPapers={load.retryPapers}
            onReplace={replace}
            onPush={push}
          />
        )}
        {state.view === "insights" &&
          (load.atlas ? (
            <InsightsView
              atlas={load.atlas}
              onOpenIdea={(selected) =>
                push({
                  view: "map",
                  selected,
                  kinds: [...ALL_NODE_KINDS],
                  query: "",
                  focus: null,
                  minFeasibility: 1,
                })
              }
            />
          ) : (
            paperFallback
          ))}
        {state.view === "library" &&
          (load.atlas ? (
            <LibraryView
              atlas={load.atlas}
              query={state.query}
              onClearQuery={() => replace({ query: "" })}
            />
          ) : (
            paperFallback
          ))}
        {state.view === "briefs" &&
          (load.atlas ? (
            <BriefsView
              atlas={load.atlas}
              query={state.query}
              onClearQuery={() => replace({ query: "" })}
            />
          ) : (
            paperFallback
          ))}
        {state.view === "coverage" &&
          (load.atlas ? <CoverageView atlas={load.atlas} /> : paperFallback)}
        {state.view === "daily" && (
          <DailyView query={state.query} onClearQuery={() => replace({ query: "" })} />
        )}
      </Suspense>
    </div>
  );
}
