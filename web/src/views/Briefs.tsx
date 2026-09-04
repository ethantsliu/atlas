import { useState } from "react";
import { ChevronRight, FlaskConical, Sparkles, Workflow } from "lucide-react";
import { BriefModal } from "../components/briefs/Brief";
import { DiscoveryReviewQueue } from "../components/briefs/Discovery";
import { PaperDetailModal } from "../components/papers/Paper";
import { EmptyState, ResultStatus } from "../components/shared/Empty";
import { PageHead } from "../components/shared/Head";
import { filterIdeaQuery, sortIdeaScores } from "../lib/filters";
import {
  ideaBasis,
  ideaRole,
  ideaStage,
  independentlyRankedIdeas,
  visibleProgramGroups,
} from "../lib/portfolio";
import { labelOf } from "../lib/text";
import type { Atlas, Idea, Paper } from "../types";

type BriefsViewProps = {
  atlas: Atlas;
  query: string;
  onClearQuery: () => void;
};

function isFeaturedDraft(idea: Idea): boolean {
  return idea.brief.status === "researched-draft";
}

export function BriefsView({ atlas, query, onClearQuery }: BriefsViewProps) {
  const [openIdea, setOpenIdea] = useState<Idea | null>(null);
  const [openPaper, setOpenPaper] = useState<Paper | null>(null);
  const ideas = filterIdeaQuery(atlas.ideas, query);
  const independentRanks = new Map(
    sortIdeaScores(independentlyRankedIdeas(atlas.ideas)).map((idea, index) => [
      idea.id,
      index + 1,
    ]),
  );
  const visibleIdeaIds = new Set(ideas.map((idea) => idea.id));
  const programGroups = visibleProgramGroups(atlas.ideas, visibleIdeaIds).map(
    ({ program, workPackages }) => ({
      program,
      workPackages: workPackages.filter(
        (workPackage) =>
          visibleIdeaIds.has(program.id) || visibleIdeaIds.has(workPackage.id),
      ),
    }),
  );
  const featuredDrafts = sortIdeaScores(
    ideas.filter((idea) => isFeaturedDraft(idea) && ideaRole(idea) === "standalone"),
  );
  const screeningCandidates = sortIdeaScores(
    ideas.filter(
      (idea) =>
        !isFeaturedDraft(idea) &&
        idea.kind === "research" &&
        ideaRole(idea) === "standalone",
    ),
  );
  const blogLeads = sortIdeaScores(
    ideas.filter(
      (idea) =>
        !isFeaturedDraft(idea) &&
        idea.kind === "blog" &&
        ideaRole(idea) === "standalone",
    ),
  );
  const researchedCount = ideas.filter(isFeaturedDraft).length;
  const screeningCount = ideas.filter(
    (idea) => !isFeaturedDraft(idea) && idea.kind === "research",
  ).length;
  const blogCount = ideas.filter(
    (idea) => !isFeaturedDraft(idea) && idea.kind === "blog",
  ).length;

  function inspectPaper(paper: Paper) {
    setOpenIdea(null);
    setOpenPaper(paper);
  }

  return (
    <main className="page">
      <PageHead
        icon={<FlaskConical />}
        kicker="Project studio"
        title={`${researchedCount} researched ${researchedCount === 1 ? "draft" : "drafts"} · ${screeningCount} screening ${screeningCount === 1 ? "candidate" : "candidates"} · ${blogCount} blog ${blogCount === 1 ? "lead" : "leads"}`}
        copy="Scores measure how readily a decisive first experiment can run, not scientific importance. Researched drafts include competitor review; screening research candidates and blog leads remain provisional routes."
      />
      <ResultStatus count={ideas.length} label="research or blog brief" query={query} />

      <DiscoveryReviewQueue query={query} />

      {ideas.length === 0 && (
        <EmptyState
          title={
            query.trim() ? `No briefs match “${query.trim()}”` : "No briefs available"
          }
          copy="Try a broader research area, technique, or paper name."
          action={query.trim() ? "Clear search" : undefined}
          onReset={query.trim() ? onClearQuery : undefined}
        />
      )}

      {programGroups.length > 0 && (
        <section className="portfolio-programs" aria-labelledby="programs-title">
          <header className="brief-section-head">
            <span>
              <Workflow size={13} /> Program architecture
            </span>
            <h2 id="programs-title">Programs and their testable work packages</h2>
            <p>
              Work-package scores estimate execution feasibility inside their parent
              program. They are shown in context and are not ranked as independent
              research programs; the parent card retains its rank across all
              independently scored research and blog briefs.
            </p>
          </header>
          <div className="portfolio-program-list">
            {programGroups.map(({ program, workPackages }) => (
              <section className="program-group" key={program.id}>
                <div className="program-primary">
                  <BriefCard
                    idea={program}
                    featured
                    independentRank={independentRanks.get(program.id)}
                    onOpen={() => setOpenIdea(program)}
                  />
                </div>
                {workPackages.length > 0 && (
                  <div className="program-work-packages">
                    <div className="program-branch" aria-hidden="true" />
                    <div>
                      <span className="work-package-kicker">
                        {workPackages.length} testable{" "}
                        {workPackages.length === 1 ? "work package" : "work packages"}
                      </span>
                      <div className="work-package-grid">
                        {sortIdeaScores(workPackages).map((workPackage) => (
                          <BriefCard
                            idea={workPackage}
                            featured
                            onOpen={() => setOpenIdea(workPackage)}
                            key={workPackage.id}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </section>
            ))}
          </div>
        </section>
      )}

      {featuredDrafts.length > 0 && (
        <section className="featured-briefs">
          <header className="brief-section-head">
            <span>
              <Sparkles size={13} /> {featuredDrafts.length} researched{" "}
              {featuredDrafts.length === 1 ? "draft" : "drafts"}
            </span>
            <h2>Deeper evidence, ranked without hiding uncertainty</h2>
            <p>
              These briefs include field comparison and a developed validation protocol.
              Their honest feasibility score may be lower than a quick screening
              estimate.
            </p>
          </header>
          <div className="card-grid featured-grid">
            {featuredDrafts.map((idea) => (
              <BriefCard
                idea={idea}
                featured
                onOpen={() => setOpenIdea(idea)}
                key={idea.id}
              />
            ))}
          </div>
        </section>
      )}

      <CandidateGroups
        screeningCandidates={screeningCandidates}
        blogLeads={blogLeads}
        onOpen={setOpenIdea}
      />

      {openIdea && (
        <BriefModal
          idea={openIdea}
          atlas={atlas}
          close={() => setOpenIdea(null)}
          onOpenIdea={setOpenIdea}
          onOpenPaper={inspectPaper}
        />
      )}
      {openPaper && (
        <PaperDetailModal paper={openPaper} close={() => setOpenPaper(null)} />
      )}
    </main>
  );
}

type CandidateGroupsProps = {
  screeningCandidates: Idea[];
  blogLeads: Idea[];
  onOpen: (idea: Idea) => void;
};

function CandidateGroups({
  screeningCandidates,
  blogLeads,
  onOpen,
}: CandidateGroupsProps) {
  return (
    <>
      {screeningCandidates.length > 0 && (
        <section className="brief-catalog">
          <header className="brief-section-head compact">
            <span>
              {screeningCandidates.length} feasibility-ranked screening{" "}
              {screeningCandidates.length === 1 ? "candidate" : "candidates"}
            </span>
            <h2>Research leads awaiting competitor review</h2>
            <p>
              These are provisional, corpus-routed hypotheses with test plans and risk
              notes. They are not researched drafts or completed novelty claims.
            </p>
          </header>
          <div className="card-grid">
            {screeningCandidates.map((idea) => (
              <BriefCard idea={idea} onOpen={() => onOpen(idea)} key={idea.id} />
            ))}
          </div>
        </section>
      )}

      {blogLeads.length > 0 && (
        <section className="brief-catalog">
          <header className="brief-section-head compact">
            <span>
              {blogLeads.length} provisional{" "}
              {blogLeads.length === 1 ? "blog lead" : "blog leads"}
            </span>
            <h2>Blog concepts awaiting source development</h2>
            <p>
              These editorial leads connect paper themes with collection evidence. They
              are not research proposals or competitor-reviewed drafts.
            </p>
          </header>
          <div className="card-grid">
            {blogLeads.map((idea) => (
              <BriefCard idea={idea} onOpen={() => onOpen(idea)} key={idea.id} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

type BriefCardProps = {
  idea: Idea;
  featured?: boolean;
  independentRank?: number;
  onOpen: () => void;
};

function BriefCard({
  idea,
  featured = false,
  independentRank,
  onOpen,
}: BriefCardProps) {
  const role = ideaRole(idea);
  const scoreLabel = idea.feasibility.screening_estimate
    ? "screening estimate"
    : role === "work-package"
      ? "module feasibility"
      : role === "program"
        ? "program feasibility"
        : "feasibility";
  const typeLabel =
    role === "program"
      ? "research program"
      : role === "work-package"
        ? "work package"
        : ideaStage(idea).toLocaleLowerCase();

  return (
    <article className={`brief-card ${featured ? "featured" : ""} ${role}`}>
      <div>
        <span className={`type-pill ${idea.kind === "blog" ? "repo" : "idea"}`}>
          {typeLabel}
        </span>
        <b className="card-score">
          {independentRank && `#${independentRank} portfolio · `}
          {idea.feasibility.score.toFixed(1)} {scoreLabel}
        </b>
      </div>
      <h2>{idea.brief.title}</h2>
      <small className="idea-basis">
        {role !== "standalone" && `${ideaStage(idea)} · `}
        {ideaBasis(idea)}
      </small>
      <p>{idea.brief.thesis}</p>
      <div className="chip-row">
        {[...idea.topic_ids, ...idea.trick_ids].map((id) => (
          <span key={id}>{labelOf(id)}</span>
        ))}
      </div>
      <button
        onClick={(event) => {
          event.currentTarget.focus({ preventScroll: true });
          onOpen();
        }}
      >
        Open brief <ChevronRight size={15} />
      </button>
    </article>
  );
}
