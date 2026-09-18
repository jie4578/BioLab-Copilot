# Architecture Decision Records

## ADR-001: Separate deterministic statistics from LLM interpretation

- **Status:** Accepted
- **Context:** Language models are useful for summarizing structured findings but are probabilistic and can invent calculations or certainty.
- **Decision:** All numeric results and scientific flags are produced by deterministic Python modules. Any future LLM receives structured results and declared context through a narrow read-only adapter and returns labeled narrative only.
- **Consequences:** The system works without network or an LLM, numeric tests are reproducible, and narrative must be distinguished from evidence. More schema and adapter work is required.

## ADR-002: Preserve original data as read-only evidence

- **Status:** Accepted
- **Context:** Silent cleaning, overwriting, or outlier deletion makes scientific review and reproduction impossible.
- **Decision:** Source bytes are preserved and hashed. QC findings mark rows/cells and propose actions; default behavior never deletes, overwrites, imputes, or silently changes source values.
- **Consequences:** Derived data needs explicit provenance and users must make any exclusion decision. Storage and review artifacts are slightly larger.

## ADR-003: Use an experiment-plugin architecture

- **Status:** Accepted
- **Context:** Assays have different layouts, assumptions, QC rules, and statistics. A single conditional pipeline would become difficult to test and extend.
- **Decision:** Keep shared contracts and orchestration separate from assay-specific plugins. Plugins declare supported experiment types, assumptions, plans, and deterministic execution behavior.
- **Consequences:** New assays can be added without rewriting the core, at the cost of an explicit interface and per-assay scientific validation.

## ADR-004: Limit the first release to two assay types

- **Status:** Accepted
- **Context:** Broad assay coverage would create unreviewed scientific rules and dilute testing effort.
- **Decision:** v1.0 plans only `generic_grouped` and `elisa_standard_curve`.
- **Consequences:** The initial product is narrower, but its contracts, QC behavior, grouped statistics, and standard-curve assumptions can receive focused review.

## ADR-005: Do not copy LIMS project code

- **Status:** Accepted
- **Context:** Existing LIMS and analysis projects may have incompatible architecture, licenses, assumptions, or security models. GPL/AGPL code is explicitly out of scope.
- **Decision:** Borrow only high-level design ideas from named references, review licenses independently, and implement original code under an MIT license with compatible dependencies.
- **Consequences:** More design work is required, while provenance, licensing, and scope remain clear.

## ADR-006: Use explicit assay contracts and user-confirmed column mappings

- **Status:** Accepted for Phase 1
- **Context:** File names and similar headers cannot reliably establish scientific meaning. The Phase 0 specification names two assay types but does not define their minimum fields or repeat metadata.
- **Decision:** `generic_grouped` requires `sample_id`, `group`, and finite numeric `measurement`. `elisa_standard_curve` requires `sample_id`, supported `sample_type`, and finite numeric `measurement`; standard rows additionally require finite numeric `standard_concentration`. The user must explicitly select the assay type and submit a source-to-canonical mapping. Suggestions are informational only.
- **Consequences:** Imports are conservative and auditable. Users must provide mapping metadata, and unsupported layouts fail visibly instead of being guessed.

## ADR-007: Preserve repeat design as metadata during ingestion

- **Status:** Accepted for Phase 1
- **Context:** Biological and technical replicates have different scientific meaning. Phase 1 lacks the experiment-design context needed to infer independence or pairing.
- **Decision:** Preserve `replicate_id`, `replicate_type`, and optional biological/technical replicate identifiers. Missing repeat type becomes `unknown` with a warning. Phase 1 never aggregates, averages, pairs, or treats technical repeats as independent biological samples.
- **Consequences:** Later statistical phases must require an explicit design confirmation before selecting tests or aggregating observations.

## ADR-008: Read CSV/XLSX conservatively with bounded resources

- **Status:** Accepted for Phase 1
- **Context:** CSV quoting, Excel formulas, macros, malformed ZIP content, and oversized workbooks can create ambiguity or resource risk.
- **Decision:** Use strict CSV parsing with explicit encoding/delimiter, `openpyxl` read-only formula-preserving mode for `.xlsx`, disabled links/macros, explicit sheet selection for multi-sheet workbooks, SHA-256 before/after checks, and configurable file/row/uncompressed-size limits.
- **Consequences:** Some inputs require a reviewed export or explicit user options. Cached formula values are never treated as scientific source values.

## ADR-009: Keep Phase 2A statistics at the measurement-row level

- **Status:** Accepted for Phase 2A
- **Context:** Phase 1 preserves biological, technical, unknown, and duplicate records but does not have enough design information to establish independent biological samples or pairing.
- **Decision:** Phase 2A computes only `n_measurements`, mean, median, min, max, and sample standard deviation (`ddof=1`) separately for each `generic_grouped` group. `independent_biological_n` remains `null`. Technical repeats, unknown repeats, duplicate records, and all source records remain unaggregated.
- **Consequences:** The output is useful for transparent distribution description without implying inferential validity. A later phase must review experimental design before choosing tests, aggregation, pairing, or biological sample units.

## ADR-010: Require explicit plan-file and hash confirmation before Phase 2A execution

- **Status:** Accepted for Phase 2A
- **Context:** A generated plan is a proposal, and either its configuration or its Phase 1 import artifact can change after generation. Silent reuse would undermine reproducibility and user review.
- **Decision:** Plan generation writes `confirmed=false`, binds the import-artifact SHA-256, source SHA-256, mapping, parser configuration, unit, analysis level, statistic set, and preservation policies. Execution requires `confirmed=true`, an explicit matching plan-file SHA-256, matching input-artifact hash, and explicit confirmation fields for duplicate-record, unknown-repeat, and single-group warnings when present.
- **Consequences:** Users must review and edit a small JSON plan before execution. There is no approval service or default “confirm all” shortcut. A changed plan or input artifact invalidates the prior confirmation.

## ADR-011: Require a separate explicit experimental-unit design declaration for Phase 2B

- **Status:** Accepted for Phase 2B
- **Context:** A `sample_id`, biological-replicate identifier, repeat type, or observed data pattern cannot establish the scientific experimental unit or independence. Treating technical rows as independent would change the estimand and uncertainty.
- **Decision:** Require a user-supplied `independent_two_group` declaration with two group names, an explicit `experimental_unit_id` field, independence rationale, repeat policy, method, alternative, alpha, confidence level, and acknowledged assumptions. Validate structure and identity consistency, but report independence as `user_declared_not_verified`.
- **Compatibility:** The additive optional fields keep contract `schema_version=1.0`; existing Phase 1 and Phase 2A JSON remains deserializable. Phase 2B execution requires the new fields to be present and valid, without changing the meaning of older plans.
- **Consequences:** Phase 2B is intentionally narrow. Missing, crossing, duplicated, or ambiguous unit identities block inference, while Phase 1 and Phase 2A preserve their original row-level behavior.

## ADR-012: Bind the Phase 2B Welch calculation to a reviewable unit preview

- **Status:** Accepted for Phase 2B
- **Context:** Technical-repeat aggregation and group assignment are scientific decisions that must be visible before a test runs. A plan confirmation is not meaningful if the preview or input can change afterward.
- **Decision:** Generate `experimental_units.json` before execution and bind its SHA-256, the Phase 1 import-artifact hash, design-file hash, mapping, and repeat policy into the plan. Recompute and compare the preview at execution. Use SciPy's supported Welch implementation with explicit two-sided settings and record its version.
- **Consequences:** Users review the exact experimental-unit assignments and aggregation before confirming. Every unit is equally weighted after an explicit within-unit mean. Preview, input, design, or plan changes invalidate the confirmation; no fallback inferential method is selected automatically.
