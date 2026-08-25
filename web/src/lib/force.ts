type ForceNode = {
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
  sx?: number;
  sy?: number;
  sz?: number;
};

export type AtlasForce = {
  (alpha: number): void;
  initialize: (nodes: ForceNode[]) => void;
};

export function pullCenter(strength = 0.055): AtlasForce {
  let nodes: ForceNode[] = [];

  const force = (alpha: number) => {
    for (const node of nodes) {
      node.vx = (node.vx ?? 0) - (node.x ?? 0) * strength * alpha;
      node.vy = (node.vy ?? 0) - (node.y ?? 0) * strength * alpha;
      node.vz = (node.vz ?? 0) - (node.z ?? 0) * strength * alpha;
    }
  };
  force.initialize = (next: ForceNode[]) => {
    nodes = next;
  };
  return force;
}

export function pullSemantic(strength = 0.11): AtlasForce {
  let nodes: ForceNode[] = [];

  const force = (alpha: number) => {
    for (const node of nodes) {
      if (node.sx == null || node.sy == null || node.sz == null) continue;
      node.vx = (node.vx ?? 0) + (node.sx - (node.x ?? 0)) * strength * alpha;
      node.vy = (node.vy ?? 0) + (node.sy - (node.y ?? 0)) * strength * alpha;
      node.vz = (node.vz ?? 0) + (node.sz - (node.z ?? 0)) * strength * alpha;
    }
  };
  force.initialize = (next: ForceNode[]) => {
    nodes = next;
  };
  return force;
}
