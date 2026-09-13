-- video-paper-wiki base-catalog-v1 structural DDL.

-- Requires SQLite >= 3.37.0 for STRICT. Enable foreign_keys per connection.

-- No business mapper, REAL/JSON/BLOB storage, custom functions, defaults or triggers.

-- Deferred FKs permit arbitrary complete-transaction insertion order; commit must validate them.

PRAGMA foreign_keys = ON;

CREATE TABLE "alignment_absence_patterns" (
  "alignment_path" TEXT COLLATE BINARY NOT NULL,
  "capability_name" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "pattern" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("alignment_path", "capability_name", "ordinal"),
  FOREIGN KEY ("alignment_path", "capability_name") REFERENCES "alignment_capabilities" ("alignment_path", "name") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "alignment_capabilities" (
  "alignment_path" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "name" TEXT COLLATE BINARY NOT NULL CHECK ("name" IN ('training', 'inference', 'data', 'evaluation', 'checkpoints')),
  "status" TEXT COLLATE BINARY NOT NULL CHECK ("status" IN ('present', 'absent', 'partial', 'unverified')),
  "absence_scope_present" INTEGER NOT NULL CHECK ("absence_scope_present" IN (0, 1)),
  "absence_commit" TEXT COLLATE BINARY,
  "absence_tree_prefix" TEXT COLLATE BINARY,
  "checkpoint_kind" TEXT COLLATE BINARY CHECK ("checkpoint_kind" IN ('link_only', 'artifact_verified')),
  PRIMARY KEY ("alignment_path", "name"),
  UNIQUE ("alignment_path", "ordinal"),
  FOREIGN KEY ("alignment_path") REFERENCES "alignment_manifests" ("input_path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CHECK ((absence_scope_present = 0 AND absence_commit IS NULL AND absence_tree_prefix IS NULL) OR (absence_scope_present = 1 AND absence_commit IS NOT NULL AND absence_tree_prefix IS NOT NULL)),
  CHECK (status <> 'absent' OR absence_scope_present = 1),
  CHECK (checkpoint_kind IS NULL OR name = 'checkpoints')
) STRICT;

CREATE TABLE "alignment_capability_locators" (
  "alignment_path" TEXT COLLATE BINARY NOT NULL,
  "capability_name" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "source_id" TEXT COLLATE BINARY NOT NULL,
  "locator_wire" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("alignment_path", "capability_name", "ordinal"),
  FOREIGN KEY ("alignment_path", "capability_name") REFERENCES "alignment_capabilities" ("alignment_path", "name") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("source_id") REFERENCES "sources" ("source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "alignment_manifests" (
  "input_path" TEXT COLLATE BINARY NOT NULL,
  "schema" TEXT COLLATE BINARY NOT NULL CHECK ("schema" IN ('video-paper-wiki.paper-code-alignment.v1')),
  "paper_id" TEXT COLLATE BINARY NOT NULL,
  "repo_id" TEXT COLLATE BINARY NOT NULL,
  "repository" TEXT COLLATE BINARY NOT NULL,
  "commit" TEXT COLLATE BINARY NOT NULL,
  "officiality" TEXT COLLATE BINARY NOT NULL CHECK ("officiality" IN ('official', 'unofficial', 'unverified_candidate')),
  "license_spdx_id" TEXT COLLATE BINARY,
  "license_notes" TEXT COLLATE BINARY NOT NULL,
  "archived" INTEGER NOT NULL CHECK ("archived" IN (0, 1)),
  PRIMARY KEY ("input_path"),
  FOREIGN KEY ("input_path") REFERENCES "canonical_inputs" ("path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("paper_id") REFERENCES "papers" ("paper_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("repo_id") REFERENCES "repos" ("repo_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "alignment_officiality_evidence" (
  "alignment_path" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "source_id" TEXT COLLATE BINARY NOT NULL,
  "locator_wire" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("alignment_path", "ordinal"),
  FOREIGN KEY ("alignment_path") REFERENCES "alignment_manifests" ("input_path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("source_id") REFERENCES "sources" ("source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "artifacts" (
  "artifact_path" TEXT COLLATE BINARY NOT NULL,
  "artifact_kind" TEXT COLLATE BINARY NOT NULL CHECK ("artifact_kind" IN ('captured-artifact', 'docling-document', 'parser-config', 'model-manifest')),
  "file_sha256" TEXT COLLATE BINARY NOT NULL,
  "size_bytes" INTEGER NOT NULL CHECK ("size_bytes" >= 0),
  PRIMARY KEY ("artifact_path"),
  UNIQUE ("artifact_path", "file_sha256"),
  FOREIGN KEY ("artifact_path", "file_sha256") REFERENCES "canonical_inputs" ("path", "file_sha256") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "assessment_events" (
  "event_id" TEXT COLLATE BINARY NOT NULL,
  "input_path" TEXT COLLATE BINARY NOT NULL,
  "schema" TEXT COLLATE BINARY NOT NULL CHECK ("schema" IN ('video-paper-wiki.assessment-event.v1')),
  "claim_id" TEXT COLLATE BINARY NOT NULL,
  "previous_event_id" TEXT COLLATE BINARY,
  "actor_kind" TEXT COLLATE BINARY NOT NULL CHECK ("actor_kind" IN ('system', 'human')),
  "transition_kind" TEXT COLLATE BINARY NOT NULL CHECK ("transition_kind" IN ('genesis', 'human_assessment', 'evidence_invalidation')),
  "from_assessment" TEXT COLLATE BINARY CHECK ("from_assessment" IN ('provisional', 'accepted', 'contested', 'unsupported', 'deprecated')),
  "to_assessment" TEXT COLLATE BINARY NOT NULL CHECK ("to_assessment" IN ('provisional', 'accepted', 'contested', 'unsupported', 'deprecated')),
  "claim_text_sha256" TEXT COLLATE BINARY NOT NULL,
  "evidence_fingerprint" TEXT COLLATE BINARY NOT NULL,
  "decided_by" TEXT COLLATE BINARY NOT NULL,
  "decided_at" TEXT COLLATE BINARY NOT NULL,
  "reason" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("event_id"),
  UNIQUE ("input_path"),
  UNIQUE ("claim_id", "event_id"),
  FOREIGN KEY ("input_path") REFERENCES "canonical_inputs" ("path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("claim_id") REFERENCES "claims" ("claim_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("claim_id", "previous_event_id") REFERENCES "assessment_events" ("claim_id", "event_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CHECK ((actor_kind = 'system' AND transition_kind = 'genesis' AND previous_event_id IS NULL AND from_assessment IS NULL AND to_assessment = 'provisional') OR (actor_kind = 'system' AND transition_kind = 'evidence_invalidation' AND previous_event_id IS NOT NULL AND from_assessment IS NOT NULL AND to_assessment = 'provisional') OR (actor_kind = 'human' AND transition_kind = 'human_assessment' AND previous_event_id IS NOT NULL AND from_assessment IS NOT NULL AND to_assessment <> 'provisional')),
  CHECK (transition_kind <> 'human_assessment' OR from_assessment <> to_assessment)
) STRICT;

CREATE TABLE "assessment_heads" (
  "claim_id" TEXT COLLATE BINARY NOT NULL,
  "head_event_id" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("claim_id"),
  FOREIGN KEY ("claim_id") REFERENCES "claims" ("claim_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("claim_id", "head_event_id") REFERENCES "assessment_events" ("claim_id", "event_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "canonical_inputs" (
  "path" TEXT COLLATE BINARY NOT NULL,
  "kind" TEXT COLLATE BINARY NOT NULL CHECK ("kind" IN ('source-ledger', 'claim-ledger', 'taxonomy', 'paper-record', 'repo-record', 'assessment-event', 'captured-artifact', 'docling-document', 'parser-config', 'model-manifest', 'run-manifest', 'code-evidence-manifest', 'alignment-manifest')),
  "file_sha256" TEXT COLLATE BINARY NOT NULL,
  "size_bytes" INTEGER NOT NULL CHECK ("size_bytes" >= 0),
  PRIMARY KEY ("path"),
  UNIQUE ("path", "file_sha256")
) STRICT;

CREATE TABLE "claim_evidence" (
  "claim_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "source_id" TEXT COLLATE BINARY NOT NULL,
  "wire_relation" TEXT COLLATE BINARY NOT NULL CHECK ("wire_relation" IN ('supports', 'contradicts', 'context')),
  "locator_wire" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("claim_id", "ordinal"),
  FOREIGN KEY ("claim_id") REFERENCES "claims" ("claim_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("source_id") REFERENCES "sources" ("source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "claim_refs" (
  "claim_id" TEXT COLLATE BINARY NOT NULL,
  "subject_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "section" TEXT COLLATE BINARY CHECK ("section" IN ('one_sentence_conclusion', 'research_question', 'method', 'representation_architecture', 'training_data', 'experiments_results', 'limitations', 'code_resources', 'evidence_status', 'related')),
  "capability" TEXT COLLATE BINARY CHECK ("capability" IN ('training', 'inference', 'data', 'evaluation', 'checkpoints')),
  "core" INTEGER CHECK ("core" IN (0, 1)),
  "lifecycle" TEXT COLLATE BINARY NOT NULL CHECK ("lifecycle" IN ('active', 'retired')),
  PRIMARY KEY ("claim_id"),
  UNIQUE ("subject_id", "ordinal"),
  FOREIGN KEY ("claim_id") REFERENCES "claims" ("claim_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("subject_id") REFERENCES "subjects" ("subject_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CHECK ((section IS NOT NULL AND core IS NOT NULL AND capability IS NULL) OR (section IS NULL AND core IS NULL AND capability IS NOT NULL))
) STRICT;

CREATE TABLE "claims" (
  "claim_id" TEXT COLLATE BINARY NOT NULL,
  "ledger_kind" TEXT COLLATE BINARY NOT NULL CHECK ("ledger_kind" IN ('claim')),
  "text" TEXT COLLATE BINARY NOT NULL,
  "risk" TEXT COLLATE BINARY NOT NULL CHECK ("risk" IN ('normal', 'high')),
  "assessment" TEXT COLLATE BINARY NOT NULL CHECK ("assessment" IN ('provisional', 'accepted', 'contested', 'unsupported', 'deprecated')),
  "confidence" TEXT COLLATE BINARY NOT NULL CHECK ("confidence" IN ('high', 'medium', 'low', 'unknown')),
  "location_path" TEXT COLLATE BINARY NOT NULL,
  "location_anchor_present" INTEGER NOT NULL CHECK ("location_anchor_present" IN (0, 1)),
  "location_anchor" TEXT COLLATE BINARY,
  "reviewed_at" TEXT COLLATE BINARY,
  "notes_present" INTEGER NOT NULL CHECK ("notes_present" IN (0, 1)),
  "notes" TEXT COLLATE BINARY,
  "supersedes_present" INTEGER NOT NULL CHECK ("supersedes_present" IN (0, 1)),
  "supersedes" TEXT COLLATE BINARY,
  PRIMARY KEY ("claim_id"),
  FOREIGN KEY ("ledger_kind") REFERENCES "ledger_meta" ("ledger_kind") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("supersedes") REFERENCES "claims" ("claim_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CHECK ("location_anchor_present" = 1 OR "location_anchor" IS NULL),
  CHECK ("notes_present" = 1 OR "notes" IS NULL),
  CHECK ("supersedes_present" = 1 OR "supersedes" IS NULL)
) STRICT;

CREATE TABLE "code_manifests" (
  "input_path" TEXT COLLATE BINARY NOT NULL,
  "schema" TEXT COLLATE BINARY NOT NULL CHECK ("schema" IN ('video-paper-wiki.code-evidence-manifest.v1')),
  "state" TEXT COLLATE BINARY NOT NULL CHECK ("state" IN ('inspected')),
  "repo_id" TEXT COLLATE BINARY NOT NULL,
  "repository" TEXT COLLATE BINARY NOT NULL,
  "commit" TEXT COLLATE BINARY NOT NULL,
  "origin_path" TEXT COLLATE BINARY NOT NULL,
  "source_id" TEXT COLLATE BINARY NOT NULL,
  "payload_sha256" TEXT COLLATE BINARY NOT NULL,
  "payload_size_bytes" INTEGER NOT NULL CHECK ("payload_size_bytes" >= 0) CHECK ("payload_size_bytes" <= 67108864),
  "media_type" TEXT COLLATE BINARY NOT NULL CHECK ("media_type" IN ('text/plain')),
  "encoding" TEXT COLLATE BINARY NOT NULL CHECK ("encoding" IN ('utf-8')),
  "line_canonicalization" TEXT COLLATE BINARY NOT NULL CHECK ("line_canonicalization" IN ('utf8-lf-v1')),
  "newline_style" TEXT COLLATE BINARY NOT NULL CHECK ("newline_style" IN ('none', 'lf', 'crlf', 'mixed')),
  "ends_with_newline" INTEGER NOT NULL CHECK ("ends_with_newline" IN (0, 1)),
  "line_count" INTEGER NOT NULL CHECK ("line_count" >= 0) CHECK ("line_count" <= 67108864),
  "normalized_sha256" TEXT COLLATE BINARY NOT NULL,
  "proposal_sha256" TEXT COLLATE BINARY NOT NULL,
  "stored_path" TEXT COLLATE BINARY NOT NULL,
  "source_identity" TEXT COLLATE BINARY NOT NULL,
  "inspection_approval_hash" TEXT COLLATE BINARY NOT NULL,
  "operation_id" TEXT COLLATE BINARY,
  "manifest_sha256" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("input_path"),
  FOREIGN KEY ("input_path") REFERENCES "canonical_inputs" ("path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("repo_id", "commit", "origin_path", "source_id") REFERENCES "code_origins" ("repo_id", "commit", "origin_path", "source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("stored_path", "payload_sha256") REFERENCES "artifacts" ("artifact_path", "file_sha256") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "code_origins" (
  "repo_id" TEXT COLLATE BINARY NOT NULL,
  "commit" TEXT COLLATE BINARY NOT NULL,
  "origin_path" TEXT COLLATE BINARY NOT NULL,
  "source_id" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("repo_id", "commit", "origin_path", "source_id"),
  FOREIGN KEY ("repo_id") REFERENCES "repos" ("repo_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("source_id") REFERENCES "sources" ("source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "ledger_meta" (
  "ledger_kind" TEXT COLLATE BINARY NOT NULL CHECK ("ledger_kind" IN ('source', 'claim')),
  "input_path" TEXT COLLATE BINARY NOT NULL,
  "schema" TEXT COLLATE BINARY NOT NULL,
  "generated_at" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("ledger_kind"),
  UNIQUE ("input_path"),
  FOREIGN KEY ("input_path") REFERENCES "canonical_inputs" ("path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CHECK ((ledger_kind = 'source' AND schema = 'claude-obsidian.source-ledger.v1' AND input_path = 'wiki/meta/ledgers/source-ledger.json') OR (ledger_kind = 'claim' AND schema = 'claude-obsidian.claim-ledger.v1' AND input_path = 'wiki/meta/ledgers/claim-ledger.json'))
) STRICT;

CREATE TABLE "paper_aliases" (
  "paper_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "alias" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("paper_id", "ordinal"),
  UNIQUE ("paper_id", "alias"),
  FOREIGN KEY ("paper_id") REFERENCES "papers" ("paper_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "paper_authors" (
  "paper_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "author" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("paper_id", "ordinal"),
  FOREIGN KEY ("paper_id") REFERENCES "papers" ("paper_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "paper_code_urls" (
  "paper_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "url" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("paper_id", "ordinal"),
  UNIQUE ("paper_id", "url"),
  FOREIGN KEY ("paper_id") REFERENCES "papers" ("paper_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "paper_sources" (
  "paper_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "source_id" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("paper_id", "ordinal"),
  UNIQUE ("paper_id", "source_id"),
  FOREIGN KEY ("paper_id") REFERENCES "papers" ("paper_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("source_id") REFERENCES "sources" ("source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "paper_taxonomy" (
  "paper_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "axis" TEXT COLLATE BINARY NOT NULL,
  "slug" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("paper_id", "ordinal"),
  FOREIGN KEY ("paper_id") REFERENCES "papers" ("paper_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("axis", "slug") REFERENCES "taxonomy_terms" ("axis", "slug") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "papers" (
  "paper_id" TEXT COLLATE BINARY NOT NULL,
  "input_path" TEXT COLLATE BINARY NOT NULL,
  "schema" TEXT COLLATE BINARY NOT NULL CHECK ("schema" IN ('video-paper-wiki.paper-record.v1')),
  "title" TEXT COLLATE BINARY NOT NULL,
  "title_zh" TEXT COLLATE BINARY NOT NULL,
  "published_at" TEXT COLLATE BINARY NOT NULL,
  "arxiv_id" TEXT COLLATE BINARY,
  "doi" TEXT COLLATE BINARY,
  "active_extraction_path" TEXT COLLATE BINARY NOT NULL,
  "active_extraction_sha256" TEXT COLLATE BINARY NOT NULL,
  "code_urls_present" INTEGER NOT NULL CHECK ("code_urls_present" IN (0, 1)),
  "created_at" TEXT COLLATE BINARY NOT NULL,
  "updated_at" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("paper_id"),
  UNIQUE ("input_path"),
  FOREIGN KEY ("input_path") REFERENCES "canonical_inputs" ("path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("active_extraction_path", "active_extraction_sha256") REFERENCES "artifacts" ("artifact_path", "file_sha256") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "repo_papers" (
  "repo_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "paper_id" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("repo_id", "ordinal"),
  UNIQUE ("repo_id", "paper_id"),
  FOREIGN KEY ("repo_id") REFERENCES "repos" ("repo_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("paper_id") REFERENCES "papers" ("paper_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "repos" (
  "repo_id" TEXT COLLATE BINARY NOT NULL,
  "input_path" TEXT COLLATE BINARY NOT NULL,
  "schema" TEXT COLLATE BINARY NOT NULL CHECK ("schema" IN ('video-paper-wiki.repo-record.v1')),
  "canonical_repository" TEXT COLLATE BINARY NOT NULL,
  "canonical_commit" TEXT COLLATE BINARY NOT NULL,
  "officiality" TEXT COLLATE BINARY NOT NULL CHECK ("officiality" IN ('official', 'unofficial', 'unverified_candidate')),
  "license_spdx_id" TEXT COLLATE BINARY,
  "license_notes" TEXT COLLATE BINARY NOT NULL,
  "archived" INTEGER CHECK ("archived" IN (0, 1)),
  "created_at" TEXT COLLATE BINARY NOT NULL,
  "updated_at" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("repo_id"),
  UNIQUE ("input_path"),
  FOREIGN KEY ("input_path") REFERENCES "canonical_inputs" ("path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "run_artifact_bindings" (
  "run_path" TEXT COLLATE BINARY NOT NULL,
  "role" TEXT COLLATE BINARY NOT NULL CHECK ("role" IN ('source', 'parser_config', 'model_manifest', 'document')),
  "artifact_path" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("run_path", "role"),
  FOREIGN KEY ("run_path") REFERENCES "run_manifests" ("input_path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("artifact_path") REFERENCES "artifacts" ("artifact_path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "run_manifests" (
  "input_path" TEXT COLLATE BINARY NOT NULL,
  "schema" TEXT COLLATE BINARY NOT NULL CHECK ("schema" IN ('video-paper-wiki.run-manifest.v1')),
  "run_id" TEXT COLLATE BINARY NOT NULL,
  "vpwiki_version" TEXT COLLATE BINARY NOT NULL,
  "python_version" TEXT COLLATE BINARY NOT NULL,
  "docling_version" TEXT COLLATE BINARY CHECK ("docling_version" IN ('2.117.0')),
  "docling_core_version" TEXT COLLATE BINARY CHECK ("docling_core_version" IN ('2.92.0')),
  "claude_obsidian_version" TEXT COLLATE BINARY,
  "input_ingest_plan_sha256" TEXT COLLATE BINARY,
  "input_prepared_sha256" TEXT COLLATE BINARY,
  "input_source_sha256" TEXT COLLATE BINARY,
  "input_parser_config_sha256" TEXT COLLATE BINARY,
  "input_model_manifest_sha256" TEXT COLLATE BINARY,
  "output_document_json_sha256" TEXT COLLATE BINARY,
  "output_draft_sha256" TEXT COLLATE BINARY,
  "output_receipt_sha256" TEXT COLLATE BINARY,
  "started_at" TEXT COLLATE BINARY NOT NULL,
  "ended_at" TEXT COLLATE BINARY NOT NULL,
  "error_code" TEXT COLLATE BINARY,
  "pipeline_fingerprint" TEXT COLLATE BINARY,
  PRIMARY KEY ("input_path"),
  FOREIGN KEY ("input_path") REFERENCES "canonical_inputs" ("path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "source_artifacts" (
  "source_id" TEXT COLLATE BINARY NOT NULL,
  "artifact_path" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("source_id"),
  FOREIGN KEY ("source_id") REFERENCES "sources" ("source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("artifact_path") REFERENCES "artifacts" ("artifact_path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "source_pages" (
  "source_id" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "page_path" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("source_id", "ordinal"),
  FOREIGN KEY ("source_id") REFERENCES "sources" ("source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "sources" (
  "source_id" TEXT COLLATE BINARY NOT NULL,
  "ledger_kind" TEXT COLLATE BINARY NOT NULL CHECK ("ledger_kind" IN ('source')),
  "origin_kind" TEXT COLLATE BINARY NOT NULL CHECK ("origin_kind" IN ('file', 'url', 'manual')),
  "origin_locator" TEXT COLLATE BINARY NOT NULL,
  "content_kind" TEXT COLLATE BINARY NOT NULL CHECK ("content_kind" IN ('document', 'webpage', 'dataset', 'image', 'audio', 'video', 'code', 'conversation', 'synthetic', 'other')),
  "title" TEXT COLLATE BINARY NOT NULL,
  "authority" TEXT COLLATE BINARY NOT NULL CHECK ("authority" IN ('official', 'primary', 'secondary', 'community', 'synthetic', 'unknown')),
  "review_status" TEXT COLLATE BINARY NOT NULL CHECK ("review_status" IN ('unreviewed', 'active', 'superseded', 'rejected')),
  "content_sha256_present" INTEGER NOT NULL CHECK ("content_sha256_present" IN (0, 1)),
  "content_sha256" TEXT COLLATE BINARY,
  "ingested_at_present" INTEGER NOT NULL CHECK ("ingested_at_present" IN (0, 1)),
  "ingested_at" TEXT COLLATE BINARY,
  "retrieved_at_present" INTEGER NOT NULL CHECK ("retrieved_at_present" IN (0, 1)),
  "retrieved_at" TEXT COLLATE BINARY,
  "refresh_due_present" INTEGER NOT NULL CHECK ("refresh_due_present" IN (0, 1)),
  "refresh_due" TEXT COLLATE BINARY,
  "independence_key_present" INTEGER NOT NULL CHECK ("independence_key_present" IN (0, 1)),
  "independence_key" TEXT COLLATE BINARY,
  "supersedes_present" INTEGER NOT NULL CHECK ("supersedes_present" IN (0, 1)),
  "supersedes" TEXT COLLATE BINARY,
  PRIMARY KEY ("source_id"),
  FOREIGN KEY ("ledger_kind") REFERENCES "ledger_meta" ("ledger_kind") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("supersedes") REFERENCES "sources" ("source_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CHECK ((content_kind = 'synthetic') = (authority = 'synthetic')),
  CHECK ("content_sha256_present" = 1 OR "content_sha256" IS NULL),
  CHECK ("ingested_at_present" = 1 OR "ingested_at" IS NULL),
  CHECK ("retrieved_at_present" = 1 OR "retrieved_at" IS NULL),
  CHECK ("refresh_due_present" = 1 OR "refresh_due" IS NULL),
  CHECK ("independence_key_present" = 1 OR "independence_key" IS NULL),
  CHECK ("supersedes_present" = 1 OR "supersedes" IS NULL)
) STRICT;

CREATE TABLE "subjects" (
  "subject_id" TEXT COLLATE BINARY NOT NULL,
  "owner_kind" TEXT COLLATE BINARY NOT NULL CHECK ("owner_kind" IN ('paper', 'repo')),
  "paper_id" TEXT COLLATE BINARY,
  "repo_id" TEXT COLLATE BINARY,
  PRIMARY KEY ("subject_id"),
  UNIQUE ("paper_id"),
  UNIQUE ("repo_id"),
  FOREIGN KEY ("paper_id") REFERENCES "papers" ("paper_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY ("repo_id") REFERENCES "repos" ("repo_id") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CHECK ((owner_kind = 'paper' AND paper_id IS NOT NULL AND repo_id IS NULL) OR (owner_kind = 'repo' AND repo_id IS NOT NULL AND paper_id IS NULL))
) STRICT;

CREATE TABLE "taxonomy_axes" (
  "axis" TEXT COLLATE BINARY NOT NULL,
  "taxonomy_path" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "label_zh" TEXT COLLATE BINARY NOT NULL,
  "label_en" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("axis"),
  UNIQUE ("taxonomy_path", "ordinal"),
  FOREIGN KEY ("taxonomy_path") REFERENCES "taxonomy_meta" ("input_path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "taxonomy_axis_aliases" (
  "axis" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "alias" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("axis", "ordinal"),
  FOREIGN KEY ("axis") REFERENCES "taxonomy_axes" ("axis") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "taxonomy_meta" (
  "input_path" TEXT COLLATE BINARY NOT NULL,
  "version" TEXT COLLATE BINARY NOT NULL,
  "unknown_terms" TEXT COLLATE BINARY NOT NULL,
  "silent_create" INTEGER NOT NULL CHECK ("silent_create" IN (0, 1)),
  "statement_en" TEXT COLLATE BINARY NOT NULL,
  "statement_zh" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("input_path"),
  FOREIGN KEY ("input_path") REFERENCES "canonical_inputs" ("path") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
  CHECK (input_path = 'taxonomy/v1.json')
) STRICT;

CREATE TABLE "taxonomy_term_aliases" (
  "axis" TEXT COLLATE BINARY NOT NULL,
  "slug" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "alias" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("axis", "slug", "ordinal"),
  FOREIGN KEY ("axis", "slug") REFERENCES "taxonomy_terms" ("axis", "slug") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE "taxonomy_terms" (
  "axis" TEXT COLLATE BINARY NOT NULL,
  "slug" TEXT COLLATE BINARY NOT NULL,
  "ordinal" INTEGER NOT NULL CHECK ("ordinal" >= 0),
  "label_zh" TEXT COLLATE BINARY NOT NULL,
  "status" TEXT COLLATE BINARY NOT NULL,
  PRIMARY KEY ("axis", "slug"),
  UNIQUE ("axis", "ordinal"),
  FOREIGN KEY ("axis") REFERENCES "taxonomy_axes" ("axis") ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT;
