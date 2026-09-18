# Synthetic template data dictionary

The Phase 0 templates are placeholders for future read-only ingestion. Values are synthetic and do not represent an experiment.

| Field | Meaning | Generic grouped | ELISA standard curve |
| --- | --- | --- | --- |
| `sample_id` | Stable sample or well label | Required | Required |
| `group` | Experimental group label | Required | Optional for standards; recommended for samples |
| `measurement` | Numeric measured response in user-declared units | Required | Required |
| `replicate` | Replicate identifier | Recommended | Recommended |
| `standard_concentration` | Known standard concentration | Not used | Required for standards; blank for unknowns |
| `sample_type` | `standard`, `sample`, `blank`, or `control` | Optional | Required |
| `unit` | User-declared measurement/concentration unit | Optional | Recommended |

Blank cells in future inputs are missing values, not zeros. Header matching and missingness policy are future Phase 1/2 behavior.

