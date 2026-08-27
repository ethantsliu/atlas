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

const PICK_SIZE = 25;
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

export type GpuHit = { distance: number; index: number };

export type GpuPick = {
  dispose: () => void;
  pick: (
    camera: Camera,
    clientX: number,
    clientY: number,
    rect: DOMRect,
    hitSize: number,
  ) => GpuHit | null;
};

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

function readHit(
  bytes: Uint8Array,
  pointX: number,
  pointY: number,
  left: number,
  top: number,
  count: number,
): number | null {
  let best = Number.POSITIVE_INFINITY;
  let picked: number | null = null;
  for (let y = 0; y < PICK_SIZE; y += 1) {
    for (let x = 0; x < PICK_SIZE; x += 1) {
      const index = readId(bytes, (y * PICK_SIZE + x) * 4);
      if (index == null || index >= count) continue;
      const dx = left + x + 0.5 - pointX;
      const dy = top + (PICK_SIZE - y - 1) + 0.5 - pointY;
      const distance = dx * dx + dy * dy;
      if (distance >= best) continue;
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
      pointSize: { value: source.material.uniforms.pointSize.value },
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
  const bytes = new Uint8Array(PICK_SIZE * PICK_SIZE * 4);
  const bufferSize = new Vector2();
  const world = new Vector3();
  const cameraAt = new Vector3();
  const clearColor = new Color();
  const viewport = new Vector4();
  const scissor = new Vector4();

  const pick = (
    camera: Camera,
    clientX: number,
    clientY: number,
    rect: DOMRect,
    hitSize: number,
  ): GpuHit | null => {
    if (
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
    source.updateWorldMatrix(true, false);
    points.matrix.copy(source.matrixWorld);
    points.matrixWorld.copy(source.matrixWorld);
    material.uniforms.pointSize.value = Math.max(
      source.material.uniforms.pointSize.value,
      hitSize,
    );
    setView(camera, width, height, left, top);
    try {
      renderer.autoClear = false;
      renderer.setRenderTarget(target);
      renderer.setClearColor(0, 0);
      renderer.clear(true, true, true);
      renderer.render(scene, camera);
      renderer.readRenderTargetPixels(target, 0, 0, PICK_SIZE, PICK_SIZE, bytes);
    } finally {
      renderer.setRenderTarget(priorTarget, priorFace, priorLevel);
      renderer.setViewport(priorViewport);
      renderer.setScissor(priorScissor);
      renderer.setScissorTest(priorTest);
      renderer.setClearColor(clearColor, priorAlpha);
      renderer.autoClear = priorAuto;
      restoreView(camera, view);
    }
    const count = Math.max(0, source.geometry.drawRange.count);
    const index = readHit(bytes, pointX, pointY, left, top, count);
    if (index == null || index * 3 + 2 >= positions.length) return null;
    world.fromArray(positions, index * 3).applyMatrix4(source.matrixWorld);
    camera.getWorldPosition(cameraAt);
    return { distance: cameraAt.distanceTo(world), index };
  };

  return {
    dispose: () => {
      scene.remove(points);
      material.dispose();
      target.dispose();
    },
    pick,
  };
}
