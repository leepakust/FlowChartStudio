# Improvements in this reviewed build

This build was reviewed against the needs of software, firmware and embedded-systems engineers.

## Core renderer

- Added semantic spec validation with grouped, human-readable errors.
- Rendering no longer mutates the caller's input dictionary.
- Added optional automatic flow/state-machine layout (`"layout": "auto"`).
- Preserved manual coordinates and manual route/lane overrides for exact design-review diagrams.
- Added optional flow/state-machine titles and made legacy `w` behave as a minimum physical width instead of being silently ignored.
- Kept and exercised the existing obstacle-aware edge routing / label-collision logic.
- Improved self-transition labels and sequence self-calls.

## Timeline

- Fixed short-duration timelines collapsing to an unreadably narrow plot.
- Added automatic event-label staggering.
- Added dynamic lane-label width.
- Very short activity bars now place labels outside the bar when needed.
- Added range warnings for bars/events outside the declared duration.

## Sequence diagrams

- Fixed clipping of the first/last participant headers.
- Added dynamic participant spacing for longer engineering component names.
- Reworked self-calls into clear orthogonal loops.
- Added optional async arrow style.
- Added optional message palette styling.

## RTOS task sequencer

Added a dedicated `tasks` renderer designed for RTOS design reviews:

- task priorities
- running / ready / blocked / suspended / ISR states
- derived CPU-ownership strip
- interrupt/event markers
- task-to-task links for notifications, queues and semaphore-style wakeups
- overlap warnings for impossible concurrent `running` task intervals
- overlap warnings for contradictory state segments on the same task

## Desktop Studio

- Added the `tasks` diagram kind.
- Added built-in examples for every diagram kind.
- Added Validate and Format JSON commands.
- Added friendly JSON line highlighting for syntax errors.
- Added SVG and PDF vector export alongside PNG.
- Added Markdown document import and diagram selection for fenced blocks.
- Renamed the window to **Engineering Diagram Studio** to match the broader product scope.

## Developer workflow

- Added a real README / quick start.
- Added `requirements.txt`.
- Added example JSON specs and rendered example images.
- Added JSON Schema files for IDE autocomplete/static validation.
- Added smoke tests for all renderers, vector export, validation and input non-mutation.
- Added a GitHub Actions test matrix for Python 3.10-3.13.
- Extended the VS Code Markdown preview integration to support `tasks` blocks.
- Kept the old CLI calling convention for backwards compatibility while adding an argparse-based CLI with auto-detection and validation.

## Still recommended before a commercial public release

1. Package and code-sign a Windows installer/executable.
2. Add an explicit long-term schema-version/migration policy.
3. Add a crash-report/log file path that is easy for users to attach to bug reports.
4. Decide product licence/open-source/commercial-licence terms before publication.
5. Update the existing DOCX manual, which predates several features in this build.
