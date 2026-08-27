import type { GraphData, GraphLink, GraphNode, GraphNodeKind } from "../types";
import type { AtlasRead } from "./payload";
import { portfolioAtScore } from "./portfolio";

export const NODE_COLORS: Record<GraphNodeKind, string> = {
  topic: "#765b91",
  trick: "#65836d",
  paper: "#6c8e95",
  idea: "#a34f59",
};

export const ALL_NODE_KINDS: readonly GraphNodeKind[] = [
  "topic",
  "trick",
  "paper",
  "idea",
];

export type GraphFilters = {
  kinds: ReadonlySet<GraphNodeKind>;
  focus: string | null;
  selected?: string | null;
  query: string;
  minFeasibility: number;
};

export function graphEndpointId(endpoint: string | GraphNode): string {
  return typeof endpoint === "string" ? endpoint : endpoint.id;
}

export function graphKey(graph: GraphData): string {
  const nodes = graph.nodes.map((node) => node.id).join("\u0000");
  const links = graph.links
    .map(
      (link) =>
        `${graphEndpointId(link.source)}\u0001${graphEndpointId(link.target)}\u0001${link.kind}`,
    )
    .join("\u0000");
  return `${nodes}\u0002${links}`;
}

export function splitPapers(graph: GraphData): {
  core: GraphData;
  papers: GraphNode[];
} {
  const papers = graph.nodes.filter((node) => node.kind === "paper");
  const core = graph.nodes.filter((node) => node.kind !== "paper");
  const ids = new Set(core.map((node) => node.id));
  return {
    papers,
    core: {
      nodes: core,
      links: graph.links.filter(
        (link) =>
          ids.has(graphEndpointId(link.source)) &&
          ids.has(graphEndpointId(link.target)),
      ),
    },
  };
}

export function largestGroup(graph: GraphData): Set<string> {
  const edges = new Map<string, Set<string>>(
    graph.nodes.map((node) => [node.id, new Set<string>()]),
  );
  for (const link of graph.links) {
    const source = graphEndpointId(link.source);
    const target = graphEndpointId(link.target);
    edges.get(source)?.add(target);
    edges.get(target)?.add(source);
  }

  const visited = new Set<string>();
  let largest = new Set<string>();
  for (const node of graph.nodes) {
    if (visited.has(node.id)) continue;
    const group = new Set<string>();
    const pending = [node.id];
    while (pending.length > 0) {
      const id = pending.pop()!;
      if (visited.has(id)) continue;
      visited.add(id);
      group.add(id);
      for (const neighbor of edges.get(id) ?? []) {
        if (!visited.has(neighbor)) pending.push(neighbor);
      }
    }
    if (group.size > largest.size) largest = group;
  }
  return largest;
}

function nodePosition(atlas: AtlasRead, nodeId: string) {
  const point = atlas.layout?.positions[nodeId];
  if (!point) return {};
  const [x, y, z] = point;
  return { x, y, z, sx: x, sy: y, sz: z };
}

export function createGraphNodes(
  atlas: AtlasRead,
  minFeasibility: number,
): GraphNode[] {
  return [
    ...atlas.topics.map<GraphNode>((topic) => ({
      id: `topic:${topic.id}`,
      label: topic.label,
      kind: "topic",
      count: topic.paper_count,
      val: 4 + Math.sqrt(topic.paper_count || 1),
      color: NODE_COLORS.topic,
      payload: topic,
      ...nodePosition(atlas, `topic:${topic.id}`),
    })),
    ...atlas.tricks.map<GraphNode>((trick) => ({
      id: `trick:${trick.id}`,
      label: trick.label,
      kind: "trick",
      count: trick.paper_count,
      val: 3 + Math.sqrt(trick.paper_count || 1),
      color: NODE_COLORS.trick,
      payload: trick,
      ...nodePosition(atlas, `trick:${trick.id}`),
    })),
    ...atlas.papers.map<GraphNode>((paper) => ({
      id: paper.id,
      label: paper.title,
      kind: "paper",
      val:
        paper.record_kind === "non_paper_context"
          ? 1.5
          : ["full_text", "verified"].includes(paper.reading_depth)
            ? 4.5
            : paper.reading_depth === "abstract"
              ? 2.4
              : 1.8,
      color: NODE_COLORS.paper,
      payload: paper,
      ...nodePosition(atlas, paper.id),
    })),
    ...portfolioAtScore(atlas.ideas, minFeasibility).map<GraphNode>((idea) => ({
      id: idea.id,
      label: idea.brief.title,
      kind: "idea",
      val: 3 + idea.feasibility.score / 2,
      color: NODE_COLORS.idea,
      payload: idea,
      ...nodePosition(atlas, idea.id),
    })),
  ];
}

export function createGraphLinks(atlas: AtlasRead): GraphLink[] {
  const paperIds = new Map<string, string[]>();
  for (const paper of atlas.papers) {
    paperIds.set(paper.id, [paper.id]);
    if (paper.stable_id) {
      const ids = paperIds.get(paper.stable_id) ?? [];
      paperIds.set(paper.stable_id, [...ids, paper.id]);
    }
  }
  const paperLinks = atlas.papers.flatMap<GraphLink>((paper) => [
    ...paper.topics.map((topic) => ({
      source: paper.id,
      target: `topic:${topic.id}`,
      kind: "topic" as const,
    })),
    ...paper.tricks.map((trick) => ({
      source: paper.id,
      target: `trick:${trick.id}`,
      kind: "trick" as const,
    })),
  ]);
  const ideaLinks = atlas.ideas.flatMap<GraphLink>((idea) => [
    ...(idea.parent_idea_id
      ? [
          {
            source: idea.id,
            target: idea.parent_idea_id,
            kind: "idea" as const,
          },
        ]
      : []),
    ...idea.topic_ids.map((topicId) => ({
      source: idea.id,
      target: `topic:${topicId}`,
      kind: "topic" as const,
    })),
    ...idea.trick_ids.map((trickId) => ({
      source: idea.id,
      target: `trick:${trickId}`,
      kind: "trick" as const,
    })),
    ...idea.brief.paper_ids.flatMap((paperId) => {
      const localIds = paperIds.get(paperId) ?? [];
      return localIds.map((localId) => ({
        source: idea.id,
        target: localId,
        kind: "paper" as const,
      }));
    }),
  ]);
  return [...paperLinks, ...ideaLinks];
}

function endpointIds(link: GraphLink): [string, string] {
  return [graphEndpointId(link.source), graphEndpointId(link.target)];
}

function neighborIds(centerIds: ReadonlySet<string>, links: GraphLink[]): Set<string> {
  const neighbors = new Set(centerIds);

  for (const link of links) {
    const [source, target] = endpointIds(link);
    if (centerIds.has(source)) neighbors.add(target);
    if (centerIds.has(target)) neighbors.add(source);
  }

  return neighbors;
}

function filterNodeIds(graph: GraphData, nodeIds: ReadonlySet<string>): GraphData {
  return {
    nodes: graph.nodes.filter((node) => nodeIds.has(node.id)),
    links: graph.links.filter((link) => {
      const [source, target] = endpointIds(link);
      return nodeIds.has(source) && nodeIds.has(target);
    }),
  };
}

function linkKey(link: GraphLink): string {
  const [source, target] = endpointIds(link).sort();
  return `${source}\u0000${target}`;
}

function paperLinks(atlas: AtlasRead, graph: GraphData, centerId: string) {
  const center = graph.nodes.find((node) => node.id === centerId);
  if (center?.kind !== "paper") return [];
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  return (atlas.layout?.neighbors[centerId] ?? [])
    .filter((entry) => nodes.has(entry.id))
    .slice(0, 6)
    .map<GraphLink>((entry) => ({
      source: centerId,
      target: entry.id,
      kind: nodes.get(entry.id)!.kind,
    }));
}

function isolateGraph(
  graph: GraphData,
  centerId: string,
  semantic: GraphLink[] = [],
): GraphData {
  const connected = graph.links.filter((link) => endpointIds(link).includes(centerId));
  const keys = new Set(connected.map(linkKey));
  const links = [...connected, ...semantic.filter((link) => !keys.has(linkKey(link)))];
  const ids = neighborIds(new Set([centerId]), links);
  return {
    nodes: graph.nodes.filter((node) => ids.has(node.id)),
    links,
  };
}

export function buildGraph(atlas: AtlasRead, filters: GraphFilters): GraphData {
  const nodes = createGraphNodes(atlas, filters.minFeasibility);
  const complete = { nodes, links: createGraphLinks(atlas) };
  const normalizedQuery = filters.query.trim().toLocaleLowerCase();
  const enabledNodeIds = new Set(
    nodes
      .filter(
        (node) =>
          filters.kinds.has(node.kind) ||
          node.id === filters.focus ||
          node.id === filters.selected ||
          (node.kind === "paper" &&
            Boolean(normalizedQuery) &&
            node.label.toLocaleLowerCase().includes(normalizedQuery)),
      )
      .map((node) => node.id),
  );

  const filtered = filterNodeIds(complete, enabledNodeIds);
  if (filters.focus) {
    const center = nodes.find((node) => node.id === filters.focus);
    const source = center?.kind === "paper" ? complete : filtered;
    return isolateGraph(
      source,
      filters.focus,
      paperLinks(atlas, source, filters.focus),
    );
  }

  let graph = filtered;
  if (normalizedQuery) {
    const matches = new Set(
      graph.nodes
        .filter((node) => node.label.toLocaleLowerCase().includes(normalizedQuery))
        .map((node) => node.id),
    );
    graph = filterNodeIds(graph, neighborIds(matches, graph.links));
  }

  return graph;
}

export function stableGraph(
  graph: GraphData,
  cache: Map<string, GraphNode>,
): GraphData {
  const nodes = graph.nodes.map((next) => {
    const prior = cache.get(next.id);
    if (!prior) {
      cache.set(next.id, next);
      return next;
    }
    const position = { x: prior.x, y: prior.y, z: prior.z };
    Object.assign(prior, next);
    if (position.x != null) prior.x = position.x;
    if (position.y != null) prior.y = position.y;
    if (position.z != null) prior.z = position.z;
    return prior;
  });
  return { nodes, links: graph.links };
}
