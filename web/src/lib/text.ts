export function labelOf(id: string): string {
  return id
    .replaceAll(/[-_]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
