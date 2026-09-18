# Template field notes

The XLSX generator creates two worksheets with stable headers and a short instruction sheet. It does not read user data or perform analysis.

## generic_grouped

Use one row per observation or replicate. Keep the original sample label, group, measurement, and replicate identifier. Do not pre-delete suspected outliers.

## elisa_standard_curve

Use one row per well or observation. Standards carry a known `standard_concentration`; unknown samples leave that field blank and use `sample_type=sample`. Keep blanks as blanks and preserve any values outside the standard range for later QC.

