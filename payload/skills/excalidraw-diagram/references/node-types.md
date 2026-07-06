# Node Types — Shape Catalog & Semantic Meaning

Every node in a project diagram must use one of the shapes below. The shape carries meaning — readers learn to associate shape with role within the system.

| Shape | Meaning | Color (fill) | When to use |
|-------|---------|--------------|-------------|
| Rectangle | Process / Transformation | `#DAE8FC` (light blue) | Code that takes input and emits output: ingestion, parsing, cleaning, analysis. |
| Rounded Rectangle | Service / External System | `#27AE60` outline (green) | Services your team operates or integrates with (queue, scheduler, internal API). |
| Diamond | Decision / Branch | `#F39C12` outline (orange) | A point where data flow forks based on a condition (validation pass/fail, route by region). |
| Cylinder | Database / Data Store | `#8E44AD` outline (purple) | Persistent storage: SQLite, Parquet files, S3 buckets, warehouse tables. |
| Parallelogram | Input / Output Data | `#7F8C8D` outline (gray) | Raw data files, exports, structured payloads at boundaries. |
| Hexagon | Manual Step / Human Action | `#FFE6CC` (light orange) | Steps requiring a human: review, approval, manual data entry, interview. |
| Cloud shape | External API / Third-party | `#85C1E9` outline (light blue) | A public data API, a membership-database export, third-party SaaS. |
| Document shape | Report / Deliverable | `#FFF2CC` (light gold) | Final outputs the client receives: docx, pdf, dashboard URL. |

## Container vs. Node

A **container** is a translucent rectangle (`#F5F5F5`) used to visually group related nodes — e.g., wrap all "Ingestion" steps in one container. Containers are not nodes themselves; they don't appear in the documentation guide and don't get an ID. They exist purely for visual grouping.

## Node ID Convention

Every node has an ID of the form `<STAGE>-<NNN>` where STAGE is one of:

- `INGEST` — anything that pulls data from a source
- `PARSE` — validation and schema enforcement
- `CLEAN` — normalization, deduplication
- `ANALYZE` — statistical or comparative analysis
- `MODEL` — predictive/projective modeling
- `STORE` — writing to a data store
- `REPORT` — generating a deliverable
- `EXTERN` — external service or API
- `MANUAL` — human action

Example: `INGEST-001`, `MODEL-003`, `REPORT-002`. Numbers are zero-padded to 3 digits and unique within a project.
