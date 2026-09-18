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

