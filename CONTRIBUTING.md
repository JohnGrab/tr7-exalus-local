# Contributing to TR7 Exalus Local

Thank you for contributing! 🎉

## Bug Reports

1. Search existing GitHub Issues first
2. Open a new issue with:
   - Clear problem description and steps to reproduce
   - Expected vs. actual behaviour
   - Home Assistant version, TR7 firmware version (if known)
   - Debug logs (see below)

**Collecting debug logs:**
```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.tr7_exalus_local: debug
```
Then: **Settings → Logs** → copy the relevant lines.

## Feature Requests

Open a GitHub Issue or Discussion describing what the feature should do and why it's useful.

## Code Contributions

### Prerequisites

- Python 3.12+
- TR7 Exalus hardware (needed for live tests; not for unit tests)

### Development Setup

```bash
git clone https://github.com/JohnGrab/tr7-exalus-local.git
cd tr7-exalus-local

python3 -m venv .venv
source .venv/bin/activate      # Linux / Mac
# .venv\Scripts\activate       # Windows

pip install -e ".[dev]"
```

### Workflow

```bash
git checkout -b feature/my-feature   # or fix/my-fix
# ... make changes ...
pytest                               # must pass before submitting
git commit -m "feat: description"
git push origin feature/my-feature
# open a Pull Request on GitHub
```

**Commit prefixes**: `feat:` · `fix:` · `docs:` · `refactor:` · `test:` · `chore:`

### Testing

#### Unit tests — no hardware required

```bash
pytest
```

Tests live in `tests/unit/` and run against mocked WebSocket data. These must always pass.

#### Live tests — hardware required

```bash
cp config.example.json config.json
# Edit config.json: fill in host, serial_number, pin

python scripts/smoke_test.py    # connect, authenticate, list devices
python scripts/interactive.py   # interactive CLI to manually drive a blind
```

#### End-to-end in Home Assistant

```bash
cp -r custom_components/tr7_exalus_local ~/.homeassistant/custom_components/
# Restart HA, add the integration, verify a cover entity appears
```

### Code Standards

- **PEP 8** style, **type hints** on all signatures
- **Async/await** throughout — no blocking calls in async context
- Logging via `_LOGGER = logging.getLogger(__name__)`

### Adding a Translation

1. Create `custom_components/tr7_exalus_local/translations/<lang>.json`
2. Copy from `en.json` and translate the strings
3. Open a Pull Request

## Pull Request Checklist

- [ ] `pytest` passes
- [ ] Tested against real TR7 hardware (if the change touches hardware interaction)
- [ ] No undocumented breaking changes
- [ ] Documentation updated where needed
- [ ] Branch up to date with `main`

## Questions?

- **GitHub Discussions** — general questions
- **GitHub Issues** — bugs and features
- **Home Assistant Forum** — community help
