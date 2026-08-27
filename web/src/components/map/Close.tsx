import { X } from "lucide-react";
import type { MouseEvent } from "react";

type CloseProps = {
  onClose: () => void;
};

function restoreGraph() {
  window.requestAnimationFrame(() => {
    document.querySelector<HTMLElement>(".graph-wrap")?.focus({ preventScroll: true });
  });
}

export function CloseButton({ onClose }: CloseProps) {
  function closePanel(event: MouseEvent<HTMLButtonElement>) {
    const keyboard = event.detail === 0;
    onClose();
    if (keyboard) restoreGraph();
  }

  return (
    <button className="icon-close" onClick={closePanel} aria-label="Close inspector">
      <X size={16} />
    </button>
  );
}
