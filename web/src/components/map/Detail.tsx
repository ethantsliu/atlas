import { cloudLod, type CloudDetail } from "../../lib/cloudview";
import "./layout.css";

type DetailProps = {
  count: number;
  detail: CloudDetail;
  onChange: (detail: CloudDetail) => void;
};

export function compactDots(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(2)}M`;
  if (count >= 1_000) return `${Math.round(count / 1_000)}K`;
  return count.toLocaleString();
}

export function CloudDetailControl({ count, detail, onChange }: DetailProps) {
  const sample = cloudLod(count);
  if (sample >= count) return null;
  return (
    <div
      className="layout-control cloud-detail-control"
      role="group"
      aria-label="historical paper dot density"
    >
      <button
        aria-pressed={detail === "sample"}
        className={detail === "sample" ? "active" : ""}
        onClick={() => onChange("sample")}
        title={`Render a stable ${sample.toLocaleString()}-paper overview`}
        type="button"
      >
        {compactDots(sample)}
      </button>
      <button
        aria-pressed={detail === "full"}
        className={detail === "full" ? "active" : ""}
        onClick={() => onChange("full")}
        title={`Render every ${count.toLocaleString()} historical paper; this may reduce frame rate`}
        type="button"
      >
        All {compactDots(count)}
      </button>
    </div>
  );
}
