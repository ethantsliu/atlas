import { useEffect, useRef, useState } from "react";

type ElementSize = { width: number; height: number };

export function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState<ElementSize>({ width: 0, height: 0 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let frame: number | undefined;

    const measure = () => {
      if (frame != null) return;
      frame = window.requestAnimationFrame(() => {
        frame = undefined;
        const bounds = element.getBoundingClientRect();
        const next = {
          width: Math.max(1, Math.floor(bounds.width)),
          height: Math.max(1, Math.floor(bounds.height)),
        };
        setSize((current) =>
          current.width === next.width && current.height === next.height
            ? current
            : next,
        );
      });
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => {
        window.cancelAnimationFrame(frame ?? 0);
        window.removeEventListener("resize", measure);
      };
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      window.cancelAnimationFrame(frame ?? 0);
      observer.disconnect();
    };
  }, []);

  return { ref, ...size };
}
