-- search-catalog-v1 R2 extension; apply after frozen base-catalog-v1.sql.
PRAGMA foreign_keys = ON;
CREATE TABLE search_catalog_meta (
 singleton INTEGER NOT NULL PRIMARY KEY CHECK(singleton=1),
 schema_version TEXT COLLATE BINARY NOT NULL CHECK(schema_version='search-catalog-v1'),
 export_version TEXT COLLATE BINARY NOT NULL CHECK(export_version='search-catalog-export-v1'),
 join_generation_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(join_generation_sha256)=64 AND join_generation_sha256 NOT GLOB '*[^0-9a-f]*'),
 mapping_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(mapping_sha256)=64 AND mapping_sha256 NOT GLOB '*[^0-9a-f]*'),
 retrieval_config_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(retrieval_config_sha256)=64 AND retrieval_config_sha256 NOT GLOB '*[^0-9a-f]*'),
 catalog_generation_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(catalog_generation_sha256)=64 AND catalog_generation_sha256 NOT GLOB '*[^0-9a-f]*'),
 base_generation_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(base_generation_sha256)=64 AND base_generation_sha256 NOT GLOB '*[^0-9a-f]*'),
 base_catalog_rows_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(base_catalog_rows_sha256)=64 AND base_catalog_rows_sha256 NOT GLOB '*[^0-9a-f]*'),
 indexed_page_set_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(indexed_page_set_sha256)=64 AND indexed_page_set_sha256 NOT GLOB '*[^0-9a-f]*'),
 compiled_page_set_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(compiled_page_set_sha256)=64 AND compiled_page_set_sha256 NOT GLOB '*[^0-9a-f]*'),
 upstream_chunk_set_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(upstream_chunk_set_sha256)=64 AND upstream_chunk_set_sha256 NOT GLOB '*[^0-9a-f]*'),
 upstream_index_raw_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(upstream_index_raw_sha256)=64 AND upstream_index_raw_sha256 NOT GLOB '*[^0-9a-f]*'),
 upstream_index_runtime_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(upstream_index_runtime_sha256)=64 AND upstream_index_runtime_sha256 NOT GLOB '*[^0-9a-f]*'),
 evidence_inventory_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(evidence_inventory_sha256)=64 AND evidence_inventory_sha256 NOT GLOB '*[^0-9a-f]*'),
 extension_ddl_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(extension_ddl_sha256)=64 AND extension_ddl_sha256 NOT GLOB '*[^0-9a-f]*'),
 extension_manifest_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(extension_manifest_sha256)=64 AND extension_manifest_sha256 NOT GLOB '*[^0-9a-f]*'),
 builder_version TEXT COLLATE BINARY NOT NULL CHECK(length(builder_version)>0)
) STRICT, WITHOUT ROWID;
CREATE TABLE search_catalog_inputs (
 input_kind TEXT COLLATE BINARY NOT NULL CHECK(input_kind IN ('indexed-page','upstream-chunk','upstream-bm25','retrieval-config')),
 path TEXT COLLATE BINARY NOT NULL CHECK(length(path)>0),
 raw_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(raw_sha256)=64 AND raw_sha256 NOT GLOB '*[^0-9a-f]*'),
 size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
 runtime_sha256 TEXT COLLATE BINARY CHECK(runtime_sha256 IS NULL OR (length(runtime_sha256)=64 AND runtime_sha256 NOT GLOB '*[^0-9a-f]*')),
 PRIMARY KEY(input_kind,path),
 UNIQUE(input_kind,path,raw_sha256)
) STRICT, WITHOUT ROWID;
CREATE TABLE search_pages (
 page_path TEXT COLLATE BINARY NOT NULL PRIMARY KEY,
 input_kind TEXT COLLATE BINARY NOT NULL CHECK(input_kind='indexed-page'),
 page_address TEXT COLLATE BINARY NOT NULL UNIQUE CHECK(length(page_address)>0),
 page_role TEXT COLLATE BINARY NOT NULL CHECK(page_role IN ('paper','code','concept','other')),
 page_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(page_sha256)=64 AND page_sha256 NOT GLOB '*[^0-9a-f]*'),
 size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
 paper_id TEXT COLLATE BINARY,
 UNIQUE(page_path,page_sha256),
 UNIQUE(page_path,page_address),
 FOREIGN KEY(input_kind,page_path,page_sha256) REFERENCES search_catalog_inputs(input_kind,path,raw_sha256) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(paper_id) REFERENCES papers(paper_id) DEFERRABLE INITIALLY DEFERRED,
 CHECK((page_role='paper' AND paper_id IS NOT NULL) OR (page_role<>'paper' AND paper_id IS NULL))
) STRICT, WITHOUT ROWID;
CREATE TABLE search_compiled_pages (
 page_path TEXT COLLATE BINARY NOT NULL PRIMARY KEY,
 compiler_role TEXT COLLATE BINARY NOT NULL CHECK(compiler_role IN ('paper','code','concept')),
 page_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(page_sha256)=64 AND page_sha256 NOT GLOB '*[^0-9a-f]*'),
 FOREIGN KEY(page_path,page_sha256) REFERENCES search_pages(page_path,page_sha256) DEFERRABLE INITIALLY DEFERRED
) STRICT, WITHOUT ROWID;
CREATE TABLE search_chunks (
 chunk_id TEXT COLLATE BINARY NOT NULL PRIMARY KEY,
 chunk_path TEXT COLLATE BINARY NOT NULL UNIQUE,
 input_kind TEXT COLLATE BINARY NOT NULL CHECK(input_kind='upstream-chunk'),
 page_path TEXT COLLATE BINARY NOT NULL,
 page_address TEXT COLLATE BINARY NOT NULL,
 chunk_index INTEGER NOT NULL CHECK(chunk_index>=0 AND chunk_index<=2147483647),
 raw_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(raw_sha256)=64 AND raw_sha256 NOT GLOB '*[^0-9a-f]*'),
 runtime_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(runtime_sha256)=64 AND runtime_sha256 NOT GLOB '*[^0-9a-f]*'),
 body_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(body_sha256)=64 AND body_sha256 NOT GLOB '*[^0-9a-f]*'),
 page_body_sha256 TEXT COLLATE BINARY NOT NULL CHECK(length(page_body_sha256)=64 AND page_body_sha256 NOT GLOB '*[^0-9a-f]*'),
 document_length INTEGER NOT NULL CHECK(document_length>=0),
 FOREIGN KEY(page_path,page_address) REFERENCES search_pages(page_path,page_address) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(input_kind,chunk_path,raw_sha256) REFERENCES search_catalog_inputs(input_kind,path,raw_sha256) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(page_address,chunk_index)
) STRICT, WITHOUT ROWID;
CREATE TABLE search_evidence_units (
 evidence_unit_id TEXT COLLATE BINARY NOT NULL PRIMARY KEY CHECK(length(evidence_unit_id)=24 AND substr(evidence_unit_id,1,4)='evu-' AND substr(evidence_unit_id,5) NOT GLOB '*[^0-9a-f]*'),
 paper_id TEXT COLLATE BINARY NOT NULL,
 claim_id TEXT COLLATE BINARY NOT NULL,
 locator_fingerprint TEXT COLLATE BINARY NOT NULL CHECK(length(locator_fingerprint)=64 AND locator_fingerprint NOT GLOB '*[^0-9a-f]*'),
 lifecycle TEXT COLLATE BINARY NOT NULL CHECK(lifecycle IN ('active','retired')),
 assessment TEXT COLLATE BINARY NOT NULL CHECK(assessment IN ('provisional','accepted','contested','unsupported','deprecated')),
 core INTEGER NOT NULL CHECK(core IN (0,1)),
 default_eligible INTEGER NOT NULL CHECK(default_eligible IN (0,1)),
 gold_eligible INTEGER NOT NULL CHECK(gold_eligible IN (0,1)),
 UNIQUE(paper_id,claim_id,locator_fingerprint),
 FOREIGN KEY(paper_id) REFERENCES papers(paper_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(claim_id) REFERENCES claims(claim_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(claim_id) REFERENCES claim_refs(claim_id) DEFERRABLE INITIALLY DEFERRED
) STRICT, WITHOUT ROWID;
CREATE TABLE search_chunk_evidence (
 chunk_id TEXT COLLATE BINARY NOT NULL,
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 evidence_unit_id TEXT COLLATE BINARY NOT NULL,
 PRIMARY KEY(chunk_id,ordinal),
 UNIQUE(chunk_id,evidence_unit_id),
 FOREIGN KEY(chunk_id) REFERENCES search_chunks(chunk_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(evidence_unit_id) REFERENCES search_evidence_units(evidence_unit_id) DEFERRABLE INITIALLY DEFERRED
) STRICT, WITHOUT ROWID;
