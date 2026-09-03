import { Share } from "../Share";
import type { LayoutMode } from "../../hooks/layout";
import { read2d, read3d, type CameraView } from "../../lib/camera";
import type { GraphNode } from "../../types";
import type { CloudDetail } from "../../lib/cloudview";
import type { GraphRef } from "./Driver";
import type { FallbackRef } from "./Fallback";
import type { RenderMode } from "./Controls";
import { CenterButton } from "./Center";
import { LayoutControl } from "./Layout";
import { NodePicker } from "./Picker";
import { ViewControl } from "./View";
import { CloudDetailControl } from "./Detail";

type ToolsProps = {
  graphRef: GraphRef;
  fallbackRef: FallbackRef;
  height: number;
  cloudCount: number;
  cloudDetail: CloudDetail;
  layout: LayoutMode;
  mode: RenderMode;
  render: RenderMode;
  nodes: GraphNode[];
  onChoose: (node: GraphNode) => void;
  onCloudDetail: (detail: CloudDetail) => void;
  onLayout: (mode: LayoutMode) => void;
  onRender: (mode: RenderMode) => void;
  selected: GraphNode | null;
  selectedId: string;
  shareUrl: (camera?: CameraView | null, render?: RenderMode) => string;
};

export function GraphTools({
  graphRef,
  fallbackRef,
  height,
  cloudCount,
  cloudDetail,
  layout,
  mode,
  render,
  nodes,
  onChoose,
  onCloudDetail,
  onLayout,
  onRender,
  selected,
  selectedId,
  shareUrl,
}: ToolsProps) {
  return (
    <>
      <NodePicker nodes={nodes} selectedId={selectedId} onChoose={onChoose} />
      <ViewControl mode={mode} onChange={onRender} />
      <LayoutControl mode={layout} onChange={onLayout} />
      {mode === "3d" && layout === "semantic" && (
        <CloudDetailControl
          count={cloudCount}
          detail={cloudDetail}
          onChange={onCloudDetail}
        />
      )}
      {selected && (
        <CenterButton
          graphRef={graphRef}
          fallbackRef={fallbackRef}
          height={height}
          mode={mode}
          selected={selected}
        />
      )}
      <Share
        getUrl={() =>
          shareUrl(
            mode === "3d"
              ? read3d(graphRef.current)
              : read2d(fallbackRef.current, height),
            render,
          )
        }
      />
    </>
  );
}
