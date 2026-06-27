# Changelog

All notable changes are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) · Versioning: [SemVer](https://semver.org/)

## [Unreleased]

### Planned
- HACS Default Repository submission
- Scenes integration
- Diagnostics platform

## [0.0.1-RC] - 2026-06-27

Release candidate for broader testing before a stable release.

### Added
- Full Home Assistant custom component for TR7 Exalus roller blinds
- Local WebSocket communication (port 81, no cloud required)
- Cover platform: open/close, precise position (0–100%), stop, real-time status updates
- Device attributes: position, state, battery level, signal strength, firmware version
- Robust connection management: auto-reconnect, keepalive, timeout handling, error recovery
- Config Flow GUI setup wizard (serial number + PIN)
- Multilingual UI: German and English
- pytest test skeleton with unit tests for state parsing (`tests/unit/`)
- Manual QA scripts: `scripts/smoke_test.py`, `scripts/interactive.py`
- HACS manifest

### Requirements
- Home Assistant ≥ 2026.4.4
- Python ≥ 3.12
- websockets ≥ 16.0
- TR7 Exalus control unit + EX-BIDI roller motors

---

## Version Numbering

- **Major** (1.x.x) — breaking changes
- **Minor** (x.1.x) — new features, backwards-compatible
- **Patch** (x.x.1) — bug fixes

## Links

- **GitHub**: https://github.com/JohnGrab/tr7-exalus-local
- **Issues**: https://github.com/JohnGrab/tr7-exalus-local/issues
- **Discussions**: https://github.com/JohnGrab/tr7-exalus-local/discussions

**[Unreleased]**: https://github.com/JohnGrab/tr7-exalus-local/compare/v0.0.1-RC...HEAD  
**[0.0.1-RC]**: https://github.com/JohnGrab/tr7-exalus-local/releases/tag/v0.0.1-RC
