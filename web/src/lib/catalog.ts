import {
  hasOnlyKeys,
  isNumber,
  isRecord,
  isString,
  isStringArray,
  type RecordValue,
} from "./guards";
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
const LENS_KEYS = new Set(["id", "label", "all_paper_count", "in_scope_paper_count"]);
const SUBJECT_KEYS = new Set(["id", "label", "paper_count", "primary_paper_count"]);
const DIRECTION_KEYS = new Set([
  "id",
  "status",
  "subject_id",
  "technique_id",
  "support_count",
  "year_count",
  "independent_author_groups_at_least",
  "npmi",
  "support_ids",
]);
const SUBJECT_ID = /^[A-Za-z][A-Za-z0-9.-]{1,31}$/;
const DIRECTION_ID = /^direction:[0-9a-f]{16}$/;
const SUPPORT_ID = /^arxiv:\S+$/;

export type CatalogSummary = {
  sourceCount: number;
  broadAreas: number;
  techniqueFamilies: number;
  arxivSubjects: number;
  eligibleDirections: number;
  candidateDirections: number;
  notice: string;
};

export type CatalogLens = {
  id: string;
  label: string;
  allPaperCount: number;
  inScopePaperCount: number;
};

export type CatalogSubject = {
  id: string;
  label: string;
  paperCount: number;
  primaryPaperCount: number;
};

export type CatalogDirection = {
  id: string;
  subjectId: string;
  techniqueId: string;
  supportCount: number;
  yearCount: number;
  npmi: number;
  supportIds: string[];
};

export type Catalog = {
  summary: CatalogSummary;
  areas: CatalogLens[];
  techniques: CatalogLens[];
  subjects: CatalogSubject[];
  directions: CatalogDirection[];
};

function whole(value: unknown): value is number {
  return isNumber(value) && Number.isInteger(value) && value >= 0;
}

function exact(value: RecordValue, keys: ReadonlySet<string>): boolean {
  return hasOnlyKeys(value, keys) && Object.keys(value).length === keys.size;
}

function readLens(value: unknown, sourceCount: number): CatalogLens | null {
  if (
    !isRecord(value) ||
    !exact(value, LENS_KEYS) ||
    !isString(value.id) ||
    !value.id ||
    !isString(value.label) ||
    !value.label ||
    !whole(value.all_paper_count) ||
    !whole(value.in_scope_paper_count) ||
    value.in_scope_paper_count > value.all_paper_count ||
    value.all_paper_count > sourceCount
  ) {
    return null;
  }
  return {
    id: value.id,
    label: value.label,
    allPaperCount: value.all_paper_count,
    inScopePaperCount: value.in_scope_paper_count,
  };
}

function readSubject(value: unknown, sourceCount: number): CatalogSubject | null {
  if (
    !isRecord(value) ||
    !exact(value, SUBJECT_KEYS) ||
    !isString(value.id) ||
    !SUBJECT_ID.test(value.id) ||
    !isString(value.label) ||
    !value.label ||
    !whole(value.paper_count) ||
    !whole(value.primary_paper_count) ||
    value.primary_paper_count > value.paper_count ||
    value.paper_count > sourceCount
  ) {
    return null;
  }
  return {
    id: value.id,
    label: value.label,
    paperCount: value.paper_count,
    primaryPaperCount: value.primary_paper_count,
  };
}

function readDirection(
  value: unknown,
  subjects: ReadonlySet<string>,
  techniques: ReadonlySet<string>,
): CatalogDirection | null {
  if (
    !isRecord(value) ||
    !exact(value, DIRECTION_KEYS) ||
    !isString(value.id) ||
    !DIRECTION_ID.test(value.id) ||
    value.status !== "candidate" ||
    !isString(value.subject_id) ||
    !subjects.has(value.subject_id) ||
    !isString(value.technique_id) ||
    !techniques.has(value.technique_id) ||
    !whole(value.support_count) ||
    value.support_count < 10 ||
    !whole(value.year_count) ||
    value.year_count < 2 ||
    value.independent_author_groups_at_least !== 3 ||
    !isNumber(value.npmi) ||
    value.npmi < -1 ||
    value.npmi > 1 ||
    !isStringArray(value.support_ids) ||
    value.support_ids.length < 1 ||
    value.support_ids.length > 6 ||
    value.support_ids.some((id) => !SUPPORT_ID.test(id)) ||
    new Set(value.support_ids).size !== value.support_ids.length
  ) {
    return null;
  }
  return {
    id: value.id,
    subjectId: value.subject_id,
    techniqueId: value.technique_id,
    supportCount: value.support_count,
    yearCount: value.year_count,
    npmi: value.npmi,
    supportIds: value.support_ids,
  };
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

export function readCatalog(value: unknown): Catalog | null {
  const summary = readCatalogSummary(value);
  if (
    !summary ||
    !isRecord(value) ||
    !Array.isArray(value.areas) ||
    !Array.isArray(value.techniques) ||
    !Array.isArray(value.subjects) ||
    !Array.isArray(value.directions)
  ) {
    return null;
  }
  const areas = value.areas.map((row) => readLens(row, summary.sourceCount));
  const techniques = value.techniques.map((row) => readLens(row, summary.sourceCount));
  const subjects = value.subjects.map((row) => readSubject(row, summary.sourceCount));
  if (
    areas.some((row) => row === null) ||
    techniques.some((row) => row === null) ||
    subjects.some((row) => row === null)
  ) {
    return null;
  }
  const validAreas = areas as CatalogLens[];
  const validTechniques = techniques as CatalogLens[];
  const validSubjects = subjects as CatalogSubject[];
  const areaIds = new Set(validAreas.map((row) => row.id));
  const techniqueIds = new Set(validTechniques.map((row) => row.id));
  const subjectIds = new Set(validSubjects.map((row) => row.id));
  if (
    validAreas.length !== summary.broadAreas ||
    validTechniques.length !== summary.techniqueFamilies ||
    validSubjects.length !== summary.arxivSubjects ||
    areaIds.size !== validAreas.length ||
    techniqueIds.size !== validTechniques.length ||
    subjectIds.size !== validSubjects.length
  ) {
    return null;
  }
  const directions = value.directions.map((row) =>
    readDirection(row, subjectIds, techniqueIds),
  );
  if (directions.some((row) => row === null)) return null;
  const validDirections = directions as CatalogDirection[];
  const directionIds = new Set(validDirections.map((row) => row.id));
  const pairs = new Set(
    validDirections.map((row) => `${row.subjectId}\u0000${row.techniqueId}`),
  );
  if (
    validDirections.length !== summary.candidateDirections ||
    directionIds.size !== validDirections.length ||
    pairs.size !== validDirections.length
  ) {
    return null;
  }
  return {
    summary,
    areas: validAreas,
    techniques: validTechniques,
    subjects: validSubjects,
    directions: validDirections,
  };
}

async function requestCatalog(
  signal: AbortSignal | undefined,
  fetcher: typeof fetch,
  base: string,
): Promise<unknown> {
  const response = await fetcher(basePath("/data/catalog.json", base), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Catalog request failed (${response.status})`);
  return response.json();
}

export async function fetchCatalogSummary(
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
  base: string = import.meta.env.BASE_URL,
): Promise<CatalogSummary> {
  const summary = readCatalogSummary(await requestCatalog(signal, fetcher, base));
  if (!summary) throw new Error("Catalog response is invalid");
  return summary;
}

export async function fetchCatalog(
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
  base: string = import.meta.env.BASE_URL,
): Promise<Catalog> {
  const catalog = readCatalog(await requestCatalog(signal, fetcher, base));
  if (!catalog) throw new Error("Catalog response is invalid");
  return catalog;
}
