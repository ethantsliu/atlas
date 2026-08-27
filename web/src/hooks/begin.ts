import { useEffect } from "react";
import type { GraphRef } from "../components/map/Driver";
import type { PickOrder } from "../lib/order";

type BeginSource = {
  addEventListener: (
    type: "pointerdown",
    listener: (event: PointerEvent) => void,
  ) => void;
  removeEventListener: (
    type: "pointerdown",
    listener: (event: PointerEvent) => void,
  ) => void;
};

export function bindBegin(source: BeginSource | null | undefined, order: PickOrder) {
  const begin = (event: PointerEvent) => order.begin(event.timeStamp);
  source?.addEventListener("pointerdown", begin);
  return () => source?.removeEventListener("pointerdown", begin);
}

export function useBegin(graphRef: GraphRef, order: PickOrder) {
  useEffect(() => {
    const canvas = graphRef.current?.renderer().domElement;
    return bindBegin(canvas, order);
  }, [graphRef, order]);
}
