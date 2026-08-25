import { Sparkles } from "lucide-react";
import { labelOf } from "../lib/text";
import type { AppView } from "./Header";

type LoaderProps = {
  view: AppView;
};

export function ViewLoader({ view }: LoaderProps) {
  return (
    <main className="loading" role="status" aria-live="polite" aria-busy="true">
      <Sparkles aria-hidden="true" /> Loading {labelOf(view)}…
    </main>
  );
}
