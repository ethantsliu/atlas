import { CAMERA_EDGE, type Camera3d } from "./camera";

type Point = { x: number; y: number; z: number };
type Controls = { target?: Point };
type Camera = { position: Point };

export function fly3d(graph: Camera3d | undefined, ratio: number): boolean {
  if (!graph || !Number.isFinite(ratio) || ratio === 0) return false;
  const camera = graph.camera() as Camera | undefined;
  const target = (graph.controls() as Controls).target;
  if (!camera?.position || !target) return false;
  const dx = target.x - camera.position.x;
  const dy = target.y - camera.position.y;
  const dz = target.z - camera.position.z;
  const distance = Math.hypot(dx, dy, dz);
  if (!Number.isFinite(distance) || distance < 0.01 || distance > 100_000) {
    return false;
  }
  const move = { x: dx * ratio, y: dy * ratio, z: dz * ratio };
  let limit = 1;
  for (const key of ["x", "y", "z"] as const) {
    const next = target[key] + move[key];
    if (move[key] > 0 && next > CAMERA_EDGE) {
      limit = Math.min(limit, (CAMERA_EDGE - target[key]) / move[key]);
    } else if (move[key] < 0 && next < -CAMERA_EDGE) {
      limit = Math.min(limit, (-CAMERA_EDGE - target[key]) / move[key]);
    }
  }
  if (limit <= 0) return false;
  move.x *= limit;
  move.y *= limit;
  move.z *= limit;
  graph.cameraPosition(
    {
      x: camera.position.x + move.x,
      y: camera.position.y + move.y,
      z: camera.position.z + move.z,
    },
    {
      x: target.x + move.x,
      y: target.y + move.y,
      z: target.z + move.z,
    },
  );
  return true;
}
