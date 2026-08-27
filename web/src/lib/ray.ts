type RayPoint = { x: number; y: number; z: number };
type RayCamera = { fov?: number; position: RayPoint };

export function hitRadius(
  camera: RayCamera,
  target: RayPoint | undefined,
  height: number,
  pixels = 6,
): number {
  if (!target || !Number.isFinite(height) || height <= 0) return 0.1;
  const distance = Math.hypot(
    camera.position.x - target.x,
    camera.position.y - target.y,
    camera.position.z - target.z,
  );
  const fov = Number.isFinite(camera.fov) ? camera.fov! : 50;
  const worldHeight = 2 * distance * Math.tan((fov * Math.PI) / 360);
  return Math.max(0.02, (worldHeight * pixels) / height);
}
