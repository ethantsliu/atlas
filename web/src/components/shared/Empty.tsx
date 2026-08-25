import { SearchX } from "lucide-react";

type ResultStatusProps = {
  count: number;
  label: string;
  plural?: string;
  query: string;
};

type EmptyStateProps = {
  title: string;
  copy: string;
  action?: string;
  onReset?: () => void;
};

function countLabel(count: number, label: string, plural?: string): string {
  return `${count.toLocaleString()} ${count === 1 ? label : (plural ?? `${label}s`)}`;
}

export function ResultStatus({ count, label, plural, query }: ResultStatusProps) {
  const result = countLabel(count, label, plural);
  const search = query.trim();

  return (
    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {search ? `${result} match “${search}”.` : `${result} available.`}
    </p>
  );
}

export function EmptyState({ title, copy, action, onReset }: EmptyStateProps) {
  return (
    <section className="empty-state" aria-labelledby="empty-state-title">
      <SearchX aria-hidden="true" />
      <div>
        <h2 id="empty-state-title">{title}</h2>
        <p>{copy}</p>
      </div>
      {action && onReset && (
        <button type="button" onClick={onReset}>
          {action}
        </button>
      )}
    </section>
  );
}
