export function basePath(
  path: string,
  base: string = import.meta.env.BASE_URL,
): string {
  const prefix = base.endsWith("/") ? base : `${base}/`;
  return `${prefix}${path.replace(/^\/+/, "")}`;
}
