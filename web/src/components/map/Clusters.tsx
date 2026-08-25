import type { ClusterRegion } from "../../lib/clusters";
import "../../cluster.css";

type ClusterPanelProps = {
  regions: readonly ClusterRegion[];
  activeId?: string | null;
  onPick?: (region: ClusterRegion) => void;
  open?: boolean;
};

function RegionName({ region }: { region: ClusterRegion }) {
  return (
    <span className="cluster-name">
      <i style={{ background: region.color }} aria-hidden="true" />
      {region.label}
    </span>
  );
}

export function ClusterPanel({ regions, activeId, onPick, open }: ClusterPanelProps) {
  const active = regions.find((region) => region.id === activeId);
  return (
    <details className="cluster-panel" open={open}>
      <summary>
        <span>coarse neighborhoods</span>
        <small>{active?.label ?? `${regions.length} groups`}</small>
      </summary>
      <div className="cluster-scroll">
        <table>
          <caption>Coarse embedding neighborhoods in the current atlas view</caption>
          <thead>
            <tr>
              <th scope="col">neighborhood</th>
              <th scope="col">entries</th>
            </tr>
          </thead>
          <tbody>
            {regions.map((region) => (
              <tr
                className={region.id === activeId ? "active" : undefined}
                key={region.id}
              >
                <th scope="row">
                  {onPick ? (
                    <button type="button" onClick={() => onPick(region)}>
                      <RegionName region={region} />
                      {region.terms.length > 0 && (
                        <small>{region.terms.slice(0, 3).join(" · ")}</small>
                      )}
                    </button>
                  ) : (
                    <RegionName region={region} />
                  )}
                </th>
                <td>{region.count.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
