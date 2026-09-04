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
  "content_sha256",
  "policy",
  "corpus",
  "coverage",
  "counts",
  "areas",
  "techniques",
  "subjects",
  "directions",
  "notice",
]);
const CORPUS_KEYS = new Set(["manifest_sha256", "source_count", "month_count"]);
const POLICY_KEYS = new Set([
  "digest",
  "identity_version",
  "ontology_sha256",
  "scopes",
  "min_direction_support",
  "min_direction_years",
  "min_author_groups",
  "max_directions",
  "published_supports",
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
  "support_refs",
]);
const SUPPORT_KEYS = new Set(["id", "month", "path", "sha256", "row"]);
const SUBJECT_ID = /^[A-Za-z][A-Za-z0-9.-]{1,31}$/;
const DIRECTION_ID = /^direction:[0-9a-f]{64}$/;
const SUPPORT_ID = /^arxiv:\S+$/;
const DIGEST = /^[0-9a-f]{64}$/;
const MONTH = /^[0-9]{4}-[0-9]{2}$/;
const SHARD = /^[0-9]{4}-[0-9]{2}(?:-[0-9a-f]{16})?\.json\.gz$/;

export type CatalogSummary = {
  corpusDigest: string;
  catalogDigest: string;
  policyDigest: string;
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

type CatalogSupport = {
  id: string;
  month: string;
  path: string;
  sha256: string;
  row: number;
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
  const supports = isRecord(value) ? value.support_refs : null;
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
    new Set(value.support_ids).size !== value.support_ids.length ||
    !Array.isArray(supports) ||
    supports.length !== value.support_ids.length
  ) {
    return null;
  }
  const supportIds = value.support_ids;
  const references: CatalogSupport[] = [];
  for (const support of supports) {
    if (
      !isRecord(support) ||
      !exact(support, SUPPORT_KEYS) ||
      !isString(support.id) ||
      !SUPPORT_ID.test(support.id) ||
      !isString(support.month) ||
      !MONTH.test(support.month) ||
      !isString(support.path) ||
      !SHARD.test(support.path) ||
      !isString(support.sha256) ||
      !DIGEST.test(support.sha256) ||
      !whole(support.row)
    ) {
      return null;
    }
    references.push(support as CatalogSupport);
  }
  if (references.some((support, index) => support.id !== supportIds[index])) {
    return null;
  }
  return {
    id: value.id,
    subjectId: value.subject_id,
    techniqueId: value.technique_id,
    supportCount: value.support_count,
    yearCount: value.year_count,
    npmi: value.npmi,
    supportIds,
  };
}

export function readCatalogSummary(value: unknown): CatalogSummary | null {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ROOT_KEYS) ||
    value.schema_version !== 1 ||
    value.status !== "corpus-derived" ||
    !isRecord(value.corpus) ||
    !exact(value.corpus, CORPUS_KEYS) ||
    !isRecord(value.policy) ||
    !exact(value.policy, POLICY_KEYS) ||
    !isRecord(value.counts) ||
    !hasOnlyKeys(value.counts, COUNT_KEYS) ||
    !isString(value.notice)
  ) {
    return null;
  }
  const corpusDigest = value.corpus.manifest_sha256;
  const catalogDigest = value.content_sha256;
  const policyDigest = value.policy.digest;
  const identityVersion = value.policy.identity_version;
  const ontologyDigest = value.policy.ontology_sha256;
  const sourceCount = value.corpus.source_count;
  const broadAreas = value.counts.broad_areas;
  const techniqueFamilies = value.counts.technique_families;
  const arxivSubjects = value.counts.arxiv_subjects;
  const eligibleDirections = value.counts.eligible_directions;
  const candidateDirections = value.counts.candidate_directions;
  if (
    !isString(corpusDigest) ||
    !DIGEST.test(corpusDigest) ||
    !isString(catalogDigest) ||
    !DIGEST.test(catalogDigest) ||
    !isString(policyDigest) ||
    !DIGEST.test(policyDigest) ||
    identityVersion !== "catalog-1" ||
    !isString(ontologyDigest) ||
    !DIGEST.test(ontologyDigest) ||
    value.generator_version !== "catalog-2" ||
    !Array.isArray(value.policy.scopes) ||
    value.policy.scopes.length !== 2 ||
    value.policy.scopes[0] !== "likely" ||
    value.policy.scopes[1] !== "possible" ||
    value.policy.min_direction_support !== 10 ||
    value.policy.min_direction_years !== 2 ||
    value.policy.min_author_groups !== 3 ||
    !whole(value.policy.max_directions) ||
    value.policy.max_directions < 1 ||
    value.policy.max_directions > 10_000 ||
    value.policy.published_supports !== 6 ||
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
    candidateDirections > value.policy.max_directions ||
    broadAreas < 1 ||
    techniqueFamilies < 1 ||
    arxivSubjects < 1
  ) {
    return null;
  }
  return {
    corpusDigest,
    catalogDigest,
    policyDigest,
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
