import {
  Camera,
  Color,
  GLSL3,
  NearestFilter,
  Points,
  RGBAFormat,
  Scene,
  ShaderMaterial,
  UnsignedByteType,
  Vector2,
  Vector3,
  Vector4,
  WebGLRenderTarget,
  type BufferGeometry,
  type WebGLRenderer,
} from "three";

export const PICK_SIZE = 51;
export const ID_SIZE = 3;
const PICK_RADIUS = (PICK_SIZE - 1) / 2;

const VERTEX = `
  uniform float pointSize;
  flat out uint pointId;
  void main() {
    pointId = uint(gl_VertexID) + 1u;
    vec4 view = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * view;
    gl_PointSize = pointSize;
  }
`;

const FRAGMENT = `
  flat in uint pointId;
  out vec4 pickColor;
  void main() {
    vec2 center = gl_PointCoord - vec2(0.5);
    float alpha = 1.0 - smoothstep(0.38, 0.5, length(center));
    if (alpha < 0.02) discard;
    pickColor = vec4(
      float(pointId & 255u),
      float((pointId >> 8u) & 255u),
      float((pointId >> 16u) & 255u),
      float((pointId >> 24u) & 255u)
    ) / 255.0;
  }
`;

type View = {
  enabled: boolean;
  fullWidth: number;
  fullHeight: number;
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
};

type ViewCamera = Camera & {
  clearViewOffset: () => void;
  setViewOffset: (
    fullWidth: number,
    fullHeight: number,
    x: number,
    y: number,
    width: number,
    height: number,
  ) => void;
  view?: View | null;
};

export type GpuHit = {
  distance: number;
  index: number;
  valid: () => boolean;
};

export type GpuPick = {
  dispose: () => void;
  pick: (
    camera: Camera,
    clientX: number,
    clientY: number,
    rect: DOMRect,
    hitSize: number,
  ) => Promise<GpuHit | null>;
};

type PickStamp = {
  camera: number[];
  count: number;
  matrix: number[];
  position: unknown;
  projection: number[];
  source: number[];
  start: number;
};

export function pickReady(source: Points<BufferGeometry, ShaderMaterial>): boolean {
  return source.userData.moving !== true;
}

export function pickIndex(
  source: Points<BufferGeometry, ShaderMaterial>,
  index: number,
): number | null {
  const position = source.geometry.getAttribute("position");
  if (position === source.userData.full) return index;
  const ids = source.userData.coarseIds;
  const coarse = source.userData.coarse;
  if (position !== coarse) return index;
  return ids instanceof Uint32Array ? (ids[index] ?? null) : index;
}

const PICK_MATRIX_EPSILON = 1e-4;

function sameValues(left: number[], right: number[]): boolean {
  return left.every(
    (value, index) => Math.abs(value - right[index]) <= PICK_MATRIX_EPSILON,
  );
}

export function stampPick(
  source: Points<BufferGeometry, ShaderMaterial>,
  camera: Camera,
): PickStamp {
  camera.updateMatrixWorld();
  source.updateWorldMatrix(true, false);
  return {
    camera: [...camera.matrixWorld.elements],
    count: source.geometry.drawRange.count,
    matrix: [...camera.matrixWorldInverse.elements],
    position: source.geometry.getAttribute("position"),
    projection: [...camera.projectionMatrix.elements],
    source: [...source.matrixWorld.elements],
    start: source.geometry.drawRange.start,
  };
}

export function validPick(
  stamp: PickStamp,
  source: Points<BufferGeometry, ShaderMaterial>,
  camera: Camera,
): boolean {
  if (!pickReady(source)) return false;
  const next = stampPick(source, camera);
  return (
    stamp.count === next.count &&
    stamp.position === next.position &&
    stamp.start === next.start &&
    sameValues(stamp.camera, next.camera) &&
    sameValues(stamp.matrix, next.matrix) &&
    sameValues(stamp.projection, next.projection) &&
    sameValues(stamp.source, next.source)
  );
}

function canView(camera: Camera): camera is ViewCamera {
  const value = camera as Partial<ViewCamera>;
  return (
    typeof value.setViewOffset === "function" &&
    typeof value.clearViewOffset === "function"
  );
}

function saveView(camera: ViewCamera): View | null {
  return camera.view ? { ...camera.view } : null;
}

function setView(
  camera: ViewCamera,
  width: number,
  height: number,
  left: number,
  top: number,
) {
  camera.setViewOffset(width, height, left, top, PICK_SIZE, PICK_SIZE);
}

function restoreView(camera: ViewCamera, view: View | null) {
  if (view?.enabled) {
    camera.setViewOffset(
      view.fullWidth,
      view.fullHeight,
      view.offsetX,
      view.offsetY,
      view.width,
      view.height,
    );
  } else {
    camera.clearViewOffset();
  }
}

function readId(bytes: Uint8Array, offset: number): number | null {
  const value =
    (bytes[offset] |
      (bytes[offset + 1] << 8) |
      (bytes[offset + 2] << 16) |
      (bytes[offset + 3] << 24)) >>>
    0;
  return value === 0 ? null : value - 1;
}

export function pickRadius(
  hitSize: number,
  width: number,
  height: number,
  rect: Pick<DOMRect, "width" | "height">,
): number {
  if (rect.width <= 0 || rect.height <= 0) return 0;
  const scale = Math.max(width / rect.width, height / rect.height);
  return Math.min(PICK_RADIUS, Math.max(0, (hitSize * scale) / 2));
}

export function readHit(
  bytes: Uint8Array,
  pointX: number,
  pointY: number,
  left: number,
  top: number,
  count: number,
  radius: number,
): number | null {
  let best = radius * radius;
  let picked: number | null = null;
  for (let y = 0; y < PICK_SIZE; y += 1) {
    for (let x = 0; x < PICK_SIZE; x += 1) {
      const index = readId(bytes, (y * PICK_SIZE + x) * 4);
      if (index == null || index >= count) continue;
      const dx = left + x + 0.5 - pointX;
      const dy = top + (PICK_SIZE - y - 1) + 0.5 - pointY;
      const distance = dx * dx + dy * dy;
      if (distance > best) continue;
      best = distance;
      picked = index;
    }
  }
  return picked;
}

export function makeGpuPick(
  renderer: WebGLRenderer,
  source: Points<BufferGeometry, ShaderMaterial>,
  positions: Float32Array,
): GpuPick {
  const material = new ShaderMaterial({
    depthTest: true,
    depthWrite: true,
    fragmentShader: FRAGMENT,
    glslVersion: GLSL3,
    toneMapped: false,
    uniforms: {
      pointSize: { value: ID_SIZE },
    },
    vertexShader: VERTEX,
  });
  const points = new Points(source.geometry, material);
  points.frustumCulled = false;
  points.matrixAutoUpdate = false;
  const scene = new Scene();
  scene.add(points);
  const target = new WebGLRenderTarget(PICK_SIZE, PICK_SIZE, {
    depthBuffer: true,
    format: RGBAFormat,
    magFilter: NearestFilter,
    minFilter: NearestFilter,
    stencilBuffer: false,
    type: UnsignedByteType,
  });
  const bufferSize = new Vector2();
  const world = new Vector3();
  const cameraAt = new Vector3();
  const clearColor = new Color();
  const viewport = new Vector4();
  const scissor = new Vector4();

  let disposed = false;
  const pick = async (
    camera: Camera,
    clientX: number,
    clientY: number,
    rect: DOMRect,
    hitSize: number,
  ): Promise<GpuHit | null> => {
    if (
      disposed ||
      !pickReady(source) ||
      renderer.getContext().isContextLost() ||
      !canView(camera) ||
      rect.width <= 0 ||
      rect.height <= 0
    ) {
      return null;
    }
    renderer.getDrawingBufferSize(bufferSize);
    const width = Math.max(1, Math.floor(bufferSize.x));
    const height = Math.max(1, Math.floor(bufferSize.y));
    const pointX = ((clientX - rect.left) / rect.width) * width;
    const pointY = ((clientY - rect.top) / rect.height) * height;
    if (pointX < 0 || pointY < 0 || pointX >= width || pointY >= height) return null;
    const left = Math.max(
      0,
      Math.min(width - PICK_SIZE, Math.floor(pointX - PICK_RADIUS)),
    );
    const top = Math.max(
      0,
      Math.min(height - PICK_SIZE, Math.floor(pointY - PICK_RADIUS)),
    );
    const stamp = stampPick(source, camera);
    const view = saveView(camera);
    const priorTarget = renderer.getRenderTarget();
    const priorFace = renderer.getActiveCubeFace();
    const priorLevel = renderer.getActiveMipmapLevel();
    const priorAlpha = renderer.getClearAlpha();
    const priorAuto = renderer.autoClear;
    const priorScissor = renderer.getScissor(scissor).clone();
    const priorTest = renderer.getScissorTest();
    const priorViewport = renderer.getViewport(viewport).clone();
    renderer.getClearColor(clearColor);
    points.matrix.copy(source.matrixWorld);
    points.matrixWorld.copy(source.matrixWorld);
    material.uniforms.pointSize.value = ID_SIZE;
    setView(camera, width, height, left, top);
    const bytes = new Uint8Array(PICK_SIZE * PICK_SIZE * 4);
    let reading: Promise<unknown>;
    try {
      renderer.autoClear = false;
      renderer.setRenderTarget(target);
      renderer.setClearColor(0, 0);
      renderer.clear(true, true, true);
      renderer.render(scene, camera);
      reading = renderer.readRenderTargetPixelsAsync(
        target,
        0,
        0,
        PICK_SIZE,
        PICK_SIZE,
        bytes,
      );
    } finally {
      renderer.setRenderTarget(priorTarget, priorFace, priorLevel);
      renderer.setViewport(priorViewport);
      renderer.setScissor(priorScissor);
      renderer.setScissorTest(priorTest);
      renderer.setClearColor(clearColor, priorAlpha);
      renderer.autoClear = priorAuto;
      restoreView(camera, view);
    }
    await reading;
    if (
      disposed ||
      renderer.getContext().isContextLost() ||
      !validPick(stamp, source, camera)
    ) {
      return null;
    }
    const count = Math.max(0, source.geometry.drawRange.count);
    const radius = pickRadius(hitSize, width, height, rect);
    const local = readHit(bytes, pointX, pointY, left, top, count, radius);
    const index = local == null ? null : pickIndex(source, local);
    if (index == null || index * 3 + 2 >= positions.length) return null;
    world.fromArray(positions, index * 3).applyMatrix4(source.matrixWorld);
    camera.getWorldPosition(cameraAt);
    return {
      distance: cameraAt.distanceTo(world),
      index,
      valid: () =>
        !disposed &&
        !renderer.getContext().isContextLost() &&
        validPick(stamp, source, camera),
    };
  };

  return {
    dispose: () => {
      disposed = true;
      scene.remove(points);
      material.dispose();
      target.dispose();
    },
    pick,
  };
}
