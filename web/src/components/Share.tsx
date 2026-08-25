import { useEffect, useState } from "react";
import { Check, Link, TriangleAlert } from "lucide-react";
import "./share.css";

type Clipboard = Pick<Navigator["clipboard"], "writeText">;

type ShareProps = {
  getUrl: () => string;
  className?: string;
};

export async function copyLink(url: string, clipboard?: Clipboard): Promise<boolean> {
  try {
    if (!clipboard) return false;
    await clipboard.writeText(url);
    return true;
  } catch {
    return false;
  }
}

export function Share({ getUrl, className = "" }: ShareProps) {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (status === "idle") return;
    const timer = window.setTimeout(() => setStatus("idle"), 1800);
    return () => window.clearTimeout(timer);
  }, [status]);

  async function copy() {
    const copied = await copyLink(getUrl(), navigator.clipboard);
    setStatus(copied ? "copied" : "failed");
  }

  return (
    <div className={`share-link ${className}`.trim()}>
      <button type="button" onClick={copy} aria-label="Copy a link to this atlas view">
        {status === "copied" ? (
          <Check size={14} aria-hidden="true" />
        ) : status === "failed" ? (
          <TriangleAlert size={14} aria-hidden="true" />
        ) : (
          <Link size={14} aria-hidden="true" />
        )}
        {status === "copied"
          ? "Copied"
          : status === "failed"
            ? "Try again"
            : "Copy view link"}
      </button>
      <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {status === "copied"
          ? "Atlas link copied to the clipboard"
          : status === "failed"
            ? "Atlas link could not be copied"
            : ""}
      </span>
    </div>
  );
}
