interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
  itemLabel: string;
}

/** "N-M of TOTAL <itemLabel>" plus Previous/Next, for any limit/offset-paginated list. */
export function Pagination({ total, limit, offset, onOffsetChange, itemLabel }: PaginationProps) {
  if (total === 0) return null;

  const start = offset + 1;
  const end = Math.min(offset + limit, total);
  const canPrevious = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className="pagination">
      <p className="table-total">
        {start}–{end} of {total} {itemLabel}
      </p>
      <div className="pagination-controls">
        <button
          type="button"
          disabled={!canPrevious}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button type="button" disabled={!canNext} onClick={() => onOffsetChange(offset + limit)}>
          Next
        </button>
      </div>
    </div>
  );
}
