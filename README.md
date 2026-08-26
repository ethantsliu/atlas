# Atlas

An interactive map of machine-learning papers, research ideas, topics, and techniques.

[Open Atlas](https://xn--rss.to/atlas/)

## Run locally

Requires Node.js 22. Docker is not required.

```bash
npm --prefix web ci
npm --prefix web run dev
```

Open `http://127.0.0.1:5173`.

## Check changes

```bash
python3 -m venv .venv
.venv/bin/pip install -r dev.txt
npm --prefix web exec playwright install chromium firefox webkit
make check PYTHON=.venv/bin/python
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development notes and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the data and embedding pipeline.

MIT licensed. Paper metadata and linked works retain their original rights; see
[NOTICE](NOTICE).
