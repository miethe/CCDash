---

## Contributing

### Development Setup

Follow the [Getting Started](#getting-started) section to set up your local environment. The full stack runs with `npm run dev`.

### Running Tests

**Frontend** (Vitest):
```bash
npm run test
```

**Backend** (pytest):
```bash
# Full test suite
backend/.venv/bin/python -m pytest backend/tests/ -v

# Single test file
backend/.venv/bin/python -m pytest backend/tests/test_sessions_parser.py -v

# Tests matching a pattern
backend/.venv/bin/python -m pytest backend/tests/ -k "test_model_identity" -v
```

### Contribution Workflow

1. Fork the repository and create a feature branch: `git checkout -b feature/my-feature`
2. Follow existing patterns — check [`CLAUDE.md`](CLAUDE.md) for architecture conventions and layering rules
3. Run both frontend and backend tests before opening a PR
4. Add tests for new backend logic; add Vitest tests for new frontend utilities
5. Document new features in the appropriate `docs/` guide
6. Open a pull request with a clear description of what changed and why

### Code Standards

- **Backend**: Routers call services/repositories only — no raw SQL in routers. Follow the layered architecture documented in `CLAUDE.md`.
- **Frontend**: All shared TypeScript interfaces live in `types.ts`. Import from `@/types`.
- **Observability**: New backend endpoints should include appropriate OpenTelemetry spans where relevant.

See [`CLAUDE.md`](CLAUDE.md) for the full development reference.
