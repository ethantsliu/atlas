import { useMemo } from "react";
import {
  countReadingDepths,
  percentageOfTotal,
  READING_DEPTHS,
  type ReadingDepthCounts,
} from "../../lib/coverage";
import { labelOf } from "../../lib/text";
import type { Paper } from "../../types";

type CoverageMiniProps = {
  papers: readonly Paper[];
  counts?: Readonly<ReadingDepthCounts>;
  total?: number;
};

export function CoverageMini({ papers, counts, total }: CoverageMiniProps) {
  const derivedCounts = useMemo(() => countReadingDepths(papers), [papers]);
  const displayedCounts = counts ?? derivedCounts;
  const displayedTotal = total ?? papers.length;

  return (
    <div className="coverage-mini">
      {READING_DEPTHS.map((level) => (
        <div key={level}>
          <span>{labelOf(level)}</span>
          <b>{displayedCounts[level] ?? 0}</b>
          <i>
            <em
              style={{
                width: `${percentageOfTotal(displayedCounts[level] ?? 0, displayedTotal)}%`,
              }}
            />
          </i>
        </div>
      ))}
    </div>
  );
}
