import type { CSSProperties } from "react";
import { pickRegions, type RegionPoint, type RegionView } from "../../lib/clusters";
import "../../cluster.css";

type RegionOverlayProps = {
  points: readonly RegionPoint[];
  view: RegionView;
};

type RegionStyle = CSSProperties & {
  "--region-color": string;
};

export function RegionOverlay({ points, view }: RegionOverlayProps) {
  const visible = pickRegions(points, view);
  return (
    <div className="region-overlay" aria-hidden="true">
      {visible.map((point) => {
        const style: RegionStyle = {
          left: point.x,
          top: point.y,
          opacity: point.opacity,
          "--region-color": point.region.color,
        };
        return (
          <span className="region-label" style={style} key={point.region.id}>
            <i />
            {point.region.label}
          </span>
        );
      })}
    </div>
  );
}
