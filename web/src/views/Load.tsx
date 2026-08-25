import { lazy } from "react";

export const BriefsView = lazy(() =>
  import("./Briefs").then((module) => ({ default: module.BriefsView })),
);

export const CoverageView = lazy(() =>
  import("./Coverage").then((module) => ({ default: module.CoverageView })),
);

export const DailyView = lazy(() =>
  import("./Daily").then((module) => ({ default: module.DailyView })),
);

export const InsightsView = lazy(() =>
  import("../Insights").then((module) => ({ default: module.default })),
);

export const LibraryView = lazy(() =>
  import("./Library").then((module) => ({ default: module.LibraryView })),
);

export const MapView = lazy(() =>
  import("./Map").then((module) => ({ default: module.MapView })),
);
