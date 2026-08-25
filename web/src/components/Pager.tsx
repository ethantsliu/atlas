type PagerProps = {
  page: number;
  total: number;
  limit: number;
  onPage: (page: number) => void;
};

export function Pager({ page, total, limit, onPage }: PagerProps) {
  const pages = Math.max(1, Math.ceil(total / limit));
  if (pages <= 1) return null;
  return (
    <nav className="pager" aria-label="Paper result pages">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>
        Page <b>{page}</b> of {pages}
      </span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </nav>
  );
}
