import { hasOnlyKeys, isNumber, isRecord, isString } from "./guards";
import { basePath } from "./paths";

const ROOT_KEYS = new Set([
  "schema_version",
  "generator_version",
  "status",
  "corpus",
  "coverage",
  "counts",
  "areas",
  "techniques",
  "subjects",
  "directions",
  "notice",
]);
const COUNT_KEYS = new Set([
  "broad_areas",
  "technique_families",
  "arxiv_subjects",
  "eligible_directions",
  "candidate_directions",
]);

export type CatalogSummary = {
  sourceCount: number;
  broadAreas: number;
  techniqueFamilies: number;
  arxivSubjects: number;
  eligibleDirections: number;
  candidateDirections: number;
  notice: string;
};

function whole(value: unknown): value is number {
  return isNumber(value) && Number.isInteger(value) && value >= 0;
}

export function readCatalogSummary(value: unknown): CatalogSummary | null {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ROOT_KEYS) ||
    value.schema_version !== 1 ||
    value.status !== "corpus-derived" ||
    !isRecord(value.corpus) ||
    !isRecord(value.counts) ||
    !hasOnlyKeys(value.counts, COUNT_KEYS) ||
    !isString(value.notice)
  ) {
    return null;
  }
  const sourceCount = value.corpus.source_count;
  const broadAreas = value.counts.broad_areas;
  const techniqueFamilies = value.counts.technique_families;
  const arxivSubjects = value.counts.arxiv_subjects;
  const eligibleDirections = value.counts.eligible_directions;
  const candidateDirections = value.counts.candidate_directions;
  if (
    !whole(sourceCount) ||
    !whole(broadAreas) ||
    !whole(techniqueFamilies) ||
    !whole(arxivSubjects) ||
    !whole(eligibleDirections) ||
    !whole(candidateDirections)
  ) {
    return null;
  }
  if (
    candidateDirections > eligibleDirections ||
    broadAreas < 1 ||
    techniqueFamilies < 1 ||
    arxivSubjects < 1
  ) {
    return null;
  }
  return {
    sourceCount,
    broadAreas,
    techniqueFamilies,
    arxivSubjects,
    eligibleDirections,
    candidateDirections,
    notice: value.notice,
  };
}

export async function fetchCatalogSummary(
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
  base: string = import.meta.env.BASE_URL,
): Promise<CatalogSummary> {
  const response = await fetcher(basePath("/data/catalog.json", base), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Catalog request failed (${response.status})`);
  const summary = readCatalogSummary(await response.json());
  if (!summary) throw new Error("Catalog response is invalid");
  return summary;
}
