begin;

revoke all on table public.feed_days from anon, authenticated;
revoke all on table public.feed_papers from anon, authenticated;
revoke all on table public.corpus_papers from anon, authenticated;
revoke all on table public.corpus_state from anon, authenticated;

grant usage on schema public to anon, authenticated;
grant select on table public.feed_days to anon, authenticated;
grant select on table public.feed_papers to anon, authenticated;
grant select on table public.corpus_papers to anon, authenticated;
grant execute on function public.search_feed(
  text, text, boolean, date, date, integer, integer
) to anon, authenticated;
grant execute on function public.search_corpus(text, integer, integer)
  to anon, authenticated;

drop policy if exists feed_days_read on public.feed_days;
create policy feed_days_read
  on public.feed_days
  for select
  to anon, authenticated
  using (true);

drop policy if exists feed_papers_read on public.feed_papers;
create policy feed_papers_read
  on public.feed_papers
  for select
  to anon, authenticated
  using (true);

drop policy if exists corpus_papers_read on public.corpus_papers;
create policy corpus_papers_read
  on public.corpus_papers
  for select
  to anon, authenticated
  using (true);

alter default privileges in schema public
  revoke all on tables from anon, authenticated;
alter default privileges in schema public
  revoke execute on functions from anon, authenticated;

commit;
