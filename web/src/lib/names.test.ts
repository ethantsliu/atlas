/// <reference types="vite/client" />

import { describe, expect, it } from "vitest";
import * as ts from "typescript";

const sources = {
  ...import.meta.glob(["../**/*.ts", "../**/*.tsx", "!../**/*.d.ts"], {
    eager: true,
    import: "default",
    query: "?raw",
  }),
  ...import.meta.glob(["../../e2e/*.ts"], {
    eager: true,
    import: "default",
    query: "?raw",
  }),
} as Record<string, string>;

function nameParts(name: string): string[] {
  return name
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .flatMap((part) => {
      if (part === part.toLowerCase() || part === part.toUpperCase()) {
        return [part];
      }
      return part.match(/[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+/g) ?? [part];
    })
    .filter((part) => !/^\d+$/.test(part));
}

function isFunction(node: ts.Node): boolean {
  return ts.isArrowFunction(node) || ts.isFunctionExpression(node);
}

function functionName(node: ts.Node): string | undefined {
  if (
    (ts.isFunctionDeclaration(node) ||
      ts.isMethodDeclaration(node) ||
      ts.isGetAccessorDeclaration(node) ||
      ts.isSetAccessorDeclaration(node)) &&
    node.name &&
    ts.isIdentifier(node.name)
  ) {
    return node.name.text;
  }
  if (
    ts.isVariableDeclaration(node) &&
    ts.isIdentifier(node.name) &&
    node.initializer &&
    isFunction(node.initializer)
  ) {
    return node.name.text;
  }
  if (
    ts.isPropertyAssignment(node) &&
    ts.isIdentifier(node.name) &&
    isFunction(node.initializer)
  ) {
    return node.name.text;
  }
  return undefined;
}

function namedFunctions(file: string, text: string): string[] {
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
  const violations: string[] = [];
  const visit = (node: ts.Node) => {
    const name = functionName(node);
    if (name) {
      const start =
        source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
      const end = source.getLineAndCharacterOfPosition(node.getEnd()).line + 1;
      if (nameParts(name).length > 3 || end - start + 1 > 180) {
        violations.push(`${file}:${start}:${name}:${end - start + 1}`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return violations;
}

describe("source names", () => {
  it("limits function names and sizes", () => {
    const violations = Object.entries(sources).flatMap(([file, text]) =>
      namedFunctions(file, text),
    );
    expect(violations).toEqual([]);
  });
});
