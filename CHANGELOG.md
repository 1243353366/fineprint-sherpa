# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog (https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Repository initialization and metadata.
- Project plan and vertical-slice specification for the Fine Print Intelligence agent.
- Remote repository: https://github.com/1243353366/fineprint-sherpa
- Initial documentation stubs (architecture, run instructions).

### Changed
- N/A

### Fixed
- N/A

### Security
- Notes about SSRF protections and credentials handling added to documentation.

### Known issues
- Remote repository creation required manual confirmation in the environment; creation completed but subsequent CI and pushes are pending implementation.
- Full retrieval/extraction/analysis pipeline not yet implemented; work begins in the next milestone.

---

## [0.1.0] - 2026-10-18
### Added
- Initial project scoping and design documents.
- MVP plan: URL → secure retrieval → text extraction → structured analysis → evidence-linked report.
- Tool registry specification and orchestration constraints.
- Typed tool schemas and acceptance criteria.
- Security, privacy, and cost-management design notes.

### Known limitations
- No backend or frontend code has yet been pushed (vertical slice to be implemented next).
- OCR support marked optional and not included in MVP scaffolding yet.

