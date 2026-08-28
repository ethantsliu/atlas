import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { labelOf } from "../../lib/text";
import type { GraphNode } from "../../types";

type PickerProps = {
  nodes: GraphNode[];
  selectedId: string;
  onChoose: (node: GraphNode) => void;
};

const DENSE_MIN = 240;
const RESULT_MAX = 16;

function sortNodes(nodes: GraphNode[]): GraphNode[] {
  return [...nodes].sort((left, right) => left.label.localeCompare(right.label));
}

function matchRank(node: GraphNode, term: string): number {
  const label = node.label.toLocaleLowerCase();
  if (label === term) return 0;
  if (label.startsWith(term)) return 1;
  return 2;
}

function matchNodes(nodes: GraphNode[], query: string): GraphNode[] {
  const term = query.trim().toLocaleLowerCase();
  if (!term) return nodes.slice(0, RESULT_MAX);
  return nodes
    .filter((node) =>
      `${labelOf(node.kind)} ${node.label}`.toLocaleLowerCase().includes(term),
    )
    .sort((left, right) => matchRank(left, term) - matchRank(right, term))
    .slice(0, RESULT_MAX);
}

function DensePicker({ nodes, selectedId, onChoose }: PickerProps) {
  const sorted = useMemo(() => sortNodes(nodes), [nodes]);
  const selected = useMemo(
    () => nodes.find((node) => node.id === selectedId),
    [nodes, selectedId],
  );
  const [query, setQuery] = useState(selected?.label ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const matches = useMemo(() => matchNodes(sorted, query), [query, sorted]);

  useEffect(() => {
    setQuery(selected?.label ?? "");
  }, [selected?.id, selected?.label]);

  const choose = (node: GraphNode) => {
    setQuery(node.label);
    setOpen(false);
    onChoose(node);
  };

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((value) =>
        matches.length ? (value + step + matches.length) % matches.length : 0,
      );
      return;
    }
    if (event.key === "Enter" && open && matches[active]) {
      event.preventDefault();
      choose(matches[active]);
    }
  };

  const expanded = open && matches.length > 0;
  return (
    <label className="graph-node-picker dense-picker">
      <span className="sr-only">Choose a visible graph node</span>
      <input
        value={query}
        role="combobox"
        autoComplete="off"
        aria-expanded={expanded}
        aria-controls="node-results"
        aria-autocomplete="list"
        aria-activedescendant={expanded ? `node-result-${active}` : undefined}
        placeholder="Find a paper or node…"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onKeyDown={onKey}
      />
      {expanded && (
        <span className="picker-results" id="node-results" role="listbox">
          {matches.map((node, index) => (
            <button
              id={`node-result-${index}`}
              type="button"
              role="option"
              tabIndex={-1}
              aria-selected={index === active}
              key={node.id}
              onPointerDown={(event) => event.preventDefault()}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(node)}
            >
              <i>{labelOf(node.kind)}</i>
              <span>{node.label}</span>
            </button>
          ))}
        </span>
      )}
      {open && matches.length === 0 && (
        <span className="picker-empty" role="status">
          No matching nodes
        </span>
      )}
    </label>
  );
}

export function NodePicker(props: PickerProps) {
  const sorted = useMemo(() => sortNodes(props.nodes), [props.nodes]);
  if (props.nodes.length >= DENSE_MIN) return <DensePicker {...props} />;

  return (
    <label className="graph-node-picker">
      <span className="sr-only">Choose a visible graph node</span>
      <select
        value={props.selectedId}
        onChange={(event) => {
          const node = props.nodes.find((item) => item.id === event.target.value);
          if (node) props.onChoose(node);
        }}
      >
        <option value="">Jump to a visible node…</option>
        {sorted.map((node) => (
          <option value={node.id} key={node.id}>
            {labelOf(node.kind)} · {node.label}
          </option>
        ))}
      </select>
    </label>
  );
}
