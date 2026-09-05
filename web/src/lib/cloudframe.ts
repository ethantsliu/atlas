import type { CloudData } from "./cloud";
import type { CameraPoint, CameraView } from "./camera";

export const CLOUD_VIEW_MARGIN = 1.32;
export const CLOUD_VIEW_HORIZONTAL_BIAS = -0.22;
export const CLOUD_VIEW_VERTICAL_BIAS = 0.14;

const HALF_FOV = (50 * Math.PI) / 360;

export type CloudFrame = {
  radius: number;
  target: CameraPoint;
};

const frames = new WeakMap<CloudData, CloudFrame>();

export function cloudFrame(data: CloudData): CloudFrame | null {
  const count = data.positions.length / 3;
  if (count < 1 || data.loaded !== count) return null;
  const cached = frames.get(data);
  if (cached) return cached;

  const low = [Infinity, Infinity, Infinity];
  const high = [-Infinity, -Infinity, -Infinity];
  for (let offset = 0; offset < data.positions.length; offset += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = data.positions[offset + axis];
      low[axis] = Math.min(low[axis], value);
      high[axis] = Math.max(high[axis], value);
    }
  }
  const target = low.map((value, axis) => (value + high[axis]) / 2) as [
    number,
    number,
    number,
  ];
  let radiusSquared = 0;
  for (let offset = 0; offset < data.positions.length; offset += 3) {
    const dx = data.positions[offset] - target[0];
    const dy = data.positions[offset + 1] - target[1];
    const dz = data.positions[offset + 2] - target[2];
    radiusSquared = Math.max(radiusSquared, dx * dx + dy * dy + dz * dz);
  }
  const frame = { radius: Math.sqrt(radiusSquared), target };
  frames.set(data, frame);
  return frame;
}

export function fitCloudView(
  data: CloudData,
  view: CameraView,
  width: number,
  height: number,
): CameraView | null {
  const frame = cloudFrame(data);
  if (!frame || width <= 0 || height <= 0) return null;
  const yaw = (view.yaw * Math.PI) / 180;
  const pitch = (view.pitch * Math.PI) / 180;
  const sinYaw = Math.sin(yaw);
  const cosYaw = Math.cos(yaw);
  const sinPitch = Math.sin(pitch);
  const cosPitch = Math.cos(pitch);
  const forward = [sinYaw * cosPitch, sinPitch, cosYaw * cosPitch];
  const right = [cosYaw, 0, -sinYaw];
  const up = [-sinYaw * sinPitch, cosPitch, -cosYaw * sinPitch];
  const aspect = width / height;
  const narrowScale = Math.max(1, height / width);
  const radius = Math.max(8, frame.radius * CLOUD_VIEW_MARGIN * narrowScale);
  const distance = radius / Math.tan(HALF_FOV);
  let projectedX = 0;
  let projectedY = 0;
  let weightX = 0;
  let weightY = 0;
  for (let offset = 0; offset < data.positions.length; offset += 3) {
    const dx = data.positions[offset] - frame.target[0];
    const dy = data.positions[offset + 1] - frame.target[1];
    const dz = data.positions[offset + 2] - frame.target[2];
    const depth = distance - (dx * forward[0] + dy * forward[1] + dz * forward[2]);
    if (depth <= 0) continue;
    const scale = depth * Math.tan(HALF_FOV);
    const xWeight = 1 / (scale * aspect);
    const yWeight = 1 / scale;
    projectedX += (dx * right[0] + dy * right[1] + dz * right[2]) * xWeight;
    projectedY += (dx * up[0] + dy * up[1] + dz * up[2]) * yWeight;
    weightX += xWeight;
    weightY += yWeight;
  }
  const shiftX =
    (weightX > 0 ? projectedX / weightX : 0) + radius * CLOUD_VIEW_HORIZONTAL_BIAS;
  const shiftY =
    (weightY > 0 ? projectedY / weightY : 0) + radius * CLOUD_VIEW_VERTICAL_BIAS;
  const target = frame.target.map(
    (value, axis) => value + shiftX * right[axis] + shiftY * up[axis],
  ) as [number, number, number];
  return {
    ...view,
    target,
    radius,
  };
}
