PYTHON ?= python3
NPM ?= npm

.PHONY: enrich feed promote data layout refresh-data generated-freshness db-migrate db-sync db-dry python-check test web-build web-budget web-e2e format-check validate check

enrich:
	$(PYTHON) pipeline/arxiv.py --resume --max-batches 0

feed:
	$(PYTHON) pipeline/feed.py --days 4

promote:
	$(PYTHON) pipeline/promote.py

db-migrate:
	$(PYTHON) pipeline/migrate.py

db-sync:
	$(PYTHON) pipeline/sync.py

db-dry:
	$(PYTHON) pipeline/sync.py --dry-run

data: enrich promote
	$(PYTHON) pipeline/assign.py
	$(PYTHON) pipeline/verify.py
	$(PYTHON) pipeline/related.py
	$(PYTHON) pipeline/atlas.py --base
	$(PYTHON) pipeline/embed.py
	$(PYTHON) pipeline/atlas.py

layout:
	$(PYTHON) pipeline/embed.py
	$(PYTHON) pipeline/atlas.py

refresh-data: data

generated-freshness:
	$(PYTHON) pipeline/validate.py --skip-dist

test:
	$(PYTHON) -m coverage erase
	$(PYTHON) -m coverage run --source=pipeline -m unittest discover -s tests -v
	$(PYTHON) -m coverage report --fail-under=50
	$(NPM) --prefix web test

python-check:
	$(PYTHON) -m py_compile pipeline/*.py tests/*.py
	ruff format --check pipeline tests
	ruff check pipeline tests

web-build:
	$(NPM) --prefix web run build

web-budget:
	$(NPM) --prefix web run test:budget

web-e2e:
	$(NPM) --prefix web run test:e2e

format-check:
	$(NPM) --prefix web run format:check

validate:
	$(PYTHON) pipeline/validate.py

check: generated-freshness
	$(MAKE) python-check
	$(MAKE) test
	$(MAKE) web-build
	$(MAKE) web-budget
	$(MAKE) web-e2e
	$(MAKE) format-check
	$(MAKE) validate
