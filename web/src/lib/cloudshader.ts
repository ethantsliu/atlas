export const CLOUD_VERTEX = `
  varying vec3 pointColor;
  varying float pointAlpha;
  uniform vec3 paperColor;
  uniform vec3 paperAccent;
  uniform vec3 paperWarm;
  uniform float cloudRadius;
  uniform float pointOpacity;
  uniform float pointSize;
  void main() {
    vec4 view = modelViewMatrix * vec4(position, 1.0);
    float radius = max(cloudRadius, 0.001);
    float inverseRadius = 1.0 / radius;
    float horizontal = clamp(position.x * inverseRadius * 0.5 + 0.5, 0.0, 1.0);
    float vertical = clamp(position.y * inverseRadius * 0.5 + 0.5, 0.0, 1.0);
    vec3 cool = mix(paperColor, paperAccent, horizontal * 0.58);
    pointColor = mix(cool, paperWarm, vertical * (0.34 - horizontal * 0.1));
    float centerDepth = -modelViewMatrix[3].z;
    float relativeDepth = clamp((-view.z - centerDepth) * inverseRadius, -1.0, 1.0);
    float radialSquared = dot(position, position) * inverseRadius * inverseRadius;
    float radial = smoothstep(0.0144, 0.6724, radialSquared);
    float density = mix(0.46, 1.0, radial);
    pointAlpha = pointOpacity * density * mix(1.12, 0.58, relativeDepth * 0.5 + 0.5);
    gl_Position = projectionMatrix * view;
    gl_PointSize = pointSize;
  }
`;
