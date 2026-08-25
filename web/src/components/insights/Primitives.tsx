import type { ReactNode } from "react";

export function VizHead({
  icon,
  title,
  copy,
}: {
  icon: ReactNode;
  title: string;
  copy: string;
}) {
  return (
    <header className="viz-head">
      <span>{icon}</span>
      <div>
        <h2>{title}</h2>
        <p>{copy}</p>
      </div>
    </header>
  );
}

export function ChartDataTable({
  label,
  columns,
  rows,
}: {
  label: string;
  columns: string[];
  rows: ReadonlyArray<ReadonlyArray<string | number>>;
}) {
  return (
    <details className="chart-data">
      <summary>View data table</summary>
      <div
        className="chart-data-scroll"
        role="region"
        aria-label={`${label} data table`}
        tabIndex={0}
      >
        <table>
          <caption className="sr-only">{label}</caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th scope="col" key={column}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`${row[0]}-${rowIndex}`}>
                {row.map((value, columnIndex) =>
                  columnIndex === 0 ? (
                    <th scope="row" key={columnIndex}>
                      {value}
                    </th>
                  ) : (
                    <td key={columnIndex}>{value}</td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
