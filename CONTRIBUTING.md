# Contributing to Vella Ops

Thank you for your interest in contributing.

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL (or use Docker)

### 1. Clone and install

```bash
git clone https://github.com/your-org/vella-ops.git
cd vella-ops

# Backend
pip install -e ".[dev]"

# Frontend
cd frontend && npm install
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY and DATABASE_URL
```

### 3. Start services

```bash
docker compose up -d   # starts PostgreSQL
uvicorn main:app --reload --port 8000
```

### 4. Run the test suite

```bash
pytest                     # backend
cd frontend && npm test    # frontend
```

### 5. Lint and type-check

```bash
ruff check src/
black --check src/
mypy src/
```

## Submitting Changes

1. **Fork** the repository and create a feature branch from `main`.
2. **Write tests** for any new behaviour (target ≥ 80% coverage).
3. **Run the full test suite** and linters before pushing.
4. **Open a pull request** against `main` and fill in the PR template.

## Code Style

- Python: [Black](https://black.readthedocs.io/) (100-char line length), [Ruff](https://docs.astral.sh/ruff/) for linting, [mypy](https://mypy.readthedocs.io/) for types.
- Frontend: Prettier + ESLint (project config).
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, etc.).

## Reporting Bugs

Open a [bug report](https://github.com/your-org/vella-ops/issues/new?template=bug_report.md). For security vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).
