import hosts from "../../../data/source/hosts.json";

export type RecordValue = Record<string, unknown>;

const PRIMARY_HOSTS = new Set(hosts);

export function isRecord(value: unknown): value is RecordValue {
  return typeof value === "object" && value !== null;
}

export function isString(value: unknown): value is string {
  return typeof value === "string";
}

export function isFilledString(value: unknown): value is string {
  return isString(value) && Boolean(value.trim());
}

export function isIsoDate(value: unknown): value is string {
  if (!isFilledString(value) || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toISOString().slice(0, 10) === value;
}

export function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

export function isFilledArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every(isFilledString);
}

export function isNumberRecord(value: unknown): boolean {
  return isRecord(value) && Object.values(value).every(isNumber);
}

export function hasOnlyKeys(value: RecordValue, allowed: ReadonlySet<string>): boolean {
  return Object.keys(value).every((key) => allowed.has(key));
}

export function hasStringFields(
  value: RecordValue,
  fields: readonly string[],
): boolean {
  return fields.every((field) => isString(value[field]));
}

export function hasFilledFields(
  value: RecordValue,
  fields: readonly string[],
): boolean {
  return fields.every((field) => isFilledString(value[field]));
}

export function optionalFilled(value: unknown): boolean {
  return value == null || isFilledString(value);
}

export function isPrimaryUrl(value: unknown): boolean {
  if (!isWebUrl(value)) return false;
  try {
    const parsed = new URL(value);
    return PRIMARY_HOSTS.has(parsed.hostname);
  } catch {
    return false;
  }
}

export function isWebUrl(value: unknown): value is string {
  if (!isFilledString(value)) return false;
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase().replace(/\.$/, "");
    const labels = host.split(".");
    return (
      parsed.protocol === "https:" &&
      !parsed.username &&
      !parsed.password &&
      (!parsed.port || parsed.port === "443") &&
      labels.length >= 2 &&
      !labels.every((label) => /^\d+$/.test(label)) &&
      !host.endsWith(".internal") &&
      !host.endsWith(".local") &&
      !host.endsWith(".localhost") &&
      labels.every((label) => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))
    );
  } catch {
    return false;
  }
}
