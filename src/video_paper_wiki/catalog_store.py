"""Deterministic SQLite projection for the verified search catalog.

The physical database is disposable.  All identities are derived from the
validated base rows, exact page/runtime bytes, mapping authority and retrieval
policy supplied by the retained collector.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import stat
import tempfile, subprocess, sys, secrets
from pathlib import Path
from typing import Any, Callable, Mapping

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.evidence_join import _inventory_digest, validate_evidence_mapping_authority
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.projection_catalog import canonical_catalog_rows
from video_paper_wiki.projection_generation import projection_generation_sha256
from video_paper_wiki.projection_runtime import runtime_projection_sha256, validate_runtime_record
from video_paper_wiki.resources import read_projection_resource_bytes
from video_paper_wiki.retrieval import derive_retrieval_config,rank_hits,validate_retrieval_config,validate_retrieval_policy
from video_paper_wiki.secure_io import load_strict_json, read_regular_file
from video_paper_wiki.upstream_runtime import bm25_query, verify_upstream

DB_RELATIVE = ".vault-meta/catalog.sqlite"
LOCK_RELATIVE = ".vault-meta/locks/catalog-build.lock"
PROFILE = "search-catalog-v1"
DDL_SHA256 = "4dfa131fd9ffc1faec7b44d1257e355d48033ebcbc4f52b2e0bb9d00b942839c"
MAX_SOURCE = 64 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")
_EXTENSION = (
    "search_catalog_inputs", "search_catalog_meta", "search_chunk_evidence",
    "search_chunks", "search_compiled_pages", "search_evidence_units", "search_pages",
)


class _RetainedFile:
    """Retain every existing parent and the final no-follow regular-file edge."""
    def __init__(self,path:Path,*,required:bool=True)->None:
        from video_paper_wiki.secure_io import dir_open_flags,file_open_flags,stamp
        self.path=path.absolute();self.edges=[];self.fd=None;self.file_stat=None
        parts=self.path.parts;fd=os.open(parts[0] or "/",dir_open_flags());self.root_fd=fd;self.root_stat=os.fstat(fd)
        try:
            for part in parts[1:-1]:
                nxt=os.open(part,dir_open_flags(),dir_fd=fd);child=os.fstat(nxt);named=os.stat(part,dir_fd=fd,follow_symlinks=False)
                if stamp(child)!=stamp(named):raise OSError
                self.edges.append((fd,part,nxt,child));fd=nxt
            self.parent_fd=fd;self.parent_stat=os.fstat(fd);self.name=parts[-1]
            try:self.fd=os.open(self.name,file_open_flags(),dir_fd=fd)
            except FileNotFoundError:
                if required:raise
                self.fd=None
            if self.fd is not None:
                self.file_stat=os.fstat(self.fd)
                if not stat.S_ISREG(self.file_stat.st_mode) or self.file_stat.st_nlink!=1:raise OSError
                named=os.stat(self.name,dir_fd=fd,follow_symlinks=False)
                if stamp(named)!=stamp(self.file_stat):raise OSError
        except BaseException:
            if self.fd is not None:
                try:os.close(self.fd)
                except OSError:pass
                self.fd=None
            for held in {self.root_fd,*(x[2] for x in self.edges)}:
                try:os.close(held)
                except OSError:pass
            _fail("CATALOG_STALE","retained catalog authority is unsafe")

    def verify(self,code:str="CATALOG_STALE")->None:
        from video_paper_wiki.secure_io import stamp
        try:
            identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
            if identity(os.fstat(self.root_fd))!=identity(self.root_stat):raise OSError
            for parent,name,child,first in self.edges:
                if identity(os.fstat(child))!=identity(first) or identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=identity(first):raise OSError
            if identity(os.fstat(self.parent_fd))!=identity(self.parent_stat):raise OSError
            try:named=os.stat(self.name,dir_fd=self.parent_fd,follow_symlinks=False)
            except FileNotFoundError:
                if self.fd is None:return
                raise
            if self.fd is None or stamp(named)!=stamp(self.file_stat) or stamp(os.fstat(self.fd))!=stamp(self.file_stat):raise OSError
        except OSError:_fail(code,"retained catalog authority changed")

    def verify_edge(self,code:str="CATALOG_STALE")->None:
        """Writer variant: allow expected directory metadata changes, retain identity and final edge."""
        from video_paper_wiki.secure_io import stamp
        try:
            for parent,name,child,first in self.edges:
                current=os.fstat(child);named_parent=os.stat(name,dir_fd=parent,follow_symlinks=False)
                identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
                if identity(current)!=identity(first) or identity(named_parent)!=identity(first):raise OSError
            current=os.fstat(self.parent_fd)
            if (current.st_dev,current.st_ino,stat.S_IMODE(current.st_mode))!=(self.parent_stat.st_dev,self.parent_stat.st_ino,stat.S_IMODE(self.parent_stat.st_mode)):raise OSError
            try:named=os.stat(self.name,dir_fd=self.parent_fd,follow_symlinks=False)
            except FileNotFoundError:
                if self.fd is None:return
                raise
            if self.fd is None or stamp(named)!=stamp(self.file_stat) or stamp(os.fstat(self.fd))!=stamp(self.file_stat):raise OSError
        except OSError:_fail(code,"retained catalog authority changed")

    def close(self)->None:
        if self.fd is not None:os.close(self.fd)
        for fd in reversed(list(dict.fromkeys([self.root_fd,*[x[2] for x in self.edges]]))):os.close(fd)


def _fail(code: str, message: str, pointer: str = "") -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exact_sha(value: object, pointer: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        _fail("CATALOG_ROWS_INVALID", "digest is not lowercase SHA-256", pointer)
    return value


def _resource(name: str) -> bytes:
    payload = read_projection_resource_bytes("catalog", name)
    if payload is None:
        _fail("CATALOG_RESOURCE_MISMATCH", "catalog resource is missing")
    return payload


def _resources() -> tuple[bytes, dict, dict, dict]:
    ddl = _resource("search-catalog-v1.sql")
    if _sha(ddl) != DDL_SHA256:
        _fail("CATALOG_RESOURCE_MISMATCH", "search catalog DDL differs")
    try:
        manifest = json.loads(_resource("search-catalog-v1.columns.json"))
        profile = json.loads(_resource("search-catalog-v1.generation-profile.json"))
        base_manifest = json.loads(_resource("base-catalog-v1.columns.json"))
    except (UnicodeError, json.JSONDecodeError):
        _fail("CATALOG_RESOURCE_MISMATCH", "catalog resource is malformed")
    if (type(manifest) is not dict or type(profile) is not dict or type(base_manifest) is not dict
            or manifest.get("ddl_sha256") != DDL_SHA256 or manifest.get("table_count") != 7
            or base_manifest.get("table_count") != 34 or profile.get("export_table_count") != 41):
        _fail("CATALOG_RESOURCE_MISMATCH", "catalog resources disagree")
    return ddl, manifest, profile, base_manifest


def retrieval_config_bytes(value: object) -> bytes:
    return canonicalize(validate_retrieval_config(value))


def _closed_material(value: object) -> dict[str, Any]:
    keys = {"base_generation_material", "base_tables", "mapping", "config", "indexed_pages",
            "compiled_pages", "chunks", "bm25", "builder_files"}
    if type(value) is not dict or set(value) != keys:
        _fail("CATALOG_INPUT_INVALID", "catalog material root is not closed")
    return value


def _bytes(value: object, pointer: str) -> bytes:
    if type(value) is not bytes:
        _fail("CATALOG_INPUT_INVALID", "source payload is not exact bytes", pointer)
    if len(value) > MAX_SOURCE:
        _fail("CATALOG_INPUT_INVALID", "source payload exceeds limit", pointer)
    return value


def _sorted_unique(items: list[dict], key: str, pointer: str) -> None:
    values = [x[key] for x in items]
    if values != sorted(values, key=lambda x: x.encode("utf-8")) or len(values) != len(set(values)):
        _fail("CATALOG_INPUT_INVALID", "catalog collection is not strictly ordered", pointer)


def prepare_catalog_material(value: object) -> dict[str, Any]:
    """Validate retained collector output and derive all four catalog digests."""
    material = _closed_material(value)
    ddl, manifest, profile, _base_manifest = _resources()
    try:
        base_raw = canonical_catalog_rows(
            generation_material=material["base_generation_material"], tables=material["base_tables"]
        )
    except ContractError as exc:
        if exc.code in {"PROJECTION_LIMIT_EXCEEDED","CATALOG_RESOURCE_MISMATCH"}:raise
        raise ContractError("CATALOG_ROWS_INVALID","base catalog material is invalid",exc.details) from None
    base_generation = projection_generation_sha256(material["base_generation_material"])
    raw_mapping=material["mapping"]
    if type(raw_mapping) is dict and "mapping_sha256" in raw_mapping:
        _exact_sha(raw_mapping["mapping_sha256"],"/mapping/mapping_sha256")
    try:mapping = validate_evidence_mapping_authority(raw_mapping)
    except ContractError as exc:
        if exc.code=="PROJECTION_LIMIT_EXCEEDED":raise
        raise ContractError("RETRIEVAL_GENERATION_MISMATCH","mapping authority is invalid",exc.details) from None
    config = validate_retrieval_config(material["config"])
    if config["generation_sha256"] != mapping["generation_sha256"] or config["mapping_sha256"] != mapping["mapping_sha256"]:
        _fail("RETRIEVAL_GENERATION_MISMATCH", "mapping and retrieval policy differ")

    pages = material["indexed_pages"]
    compiled = material["compiled_pages"]
    chunks = material["chunks"]
    bm25 = material["bm25"]
    if any(type(x) is not list for x in (pages, compiled, chunks)) or type(bm25) is not dict:
        _fail("CATALOG_INPUT_INVALID", "runtime collections have invalid shape")
    _sorted_unique(pages, "path", "/indexed_pages")
    _sorted_unique(compiled, "path", "/compiled_pages")
    _sorted_unique(chunks, "path", "/chunks")

    base_tables = {x["name"]: x for x in material["base_tables"]}
    paper_cols = base_tables.get("papers", {}).get("columns", [])
    paper_rows = base_tables.get("papers", {}).get("rows", [])
    paper_map = {dict(zip(paper_cols, row))["paper_id"]: dict(zip(paper_cols, row)) for row in paper_rows}
    page_rows: list[dict] = []
    input_rows: list[dict] = []
    page_by_path: dict[str, dict] = {}
    for i, item in enumerate(pages):
        expected = {"path", "role", "bytes", "paper_id", "page_address"}
        if type(item) is not dict or set(item) != expected:
            _fail("CATALOG_INPUT_INVALID", "indexed page descriptor is not closed", f"/indexed_pages/{i}")
        path, role, paper_id = item["path"], item["role"], item["paper_id"]
        raw = _bytes(item["bytes"], f"/indexed_pages/{i}/bytes")
        if type(path) is not str or not path.startswith("wiki/") or not path.endswith(".md") or role not in {"paper","code","concept","other"}:
            _fail("CATALOG_INPUT_INVALID", "indexed page descriptor is invalid", f"/indexed_pages/{i}")
        if (role == "paper") != (type(paper_id) is str):
            _fail("CATALOG_ROWS_INVALID", "paper role and owner differ", f"/indexed_pages/{i}/paper_id")
        if role == "paper":
            owner = paper_map.get(paper_id)
            if owner is None:
                _fail("CATALOG_ROWS_INVALID", "paper owner is absent", f"/indexed_pages/{i}/paper_id")
            from video_paper_wiki.identity import paper_page_slug
            if path != f"wiki/papers/{paper_page_slug(paper_id)}.md":
                _fail("CATALOG_ROWS_INVALID", "paper path and owner differ", f"/indexed_pages/{i}/path")
        digest = _sha(raw)
        row = {"page_path": path, "input_kind":"indexed-page", "page_address":item["page_address"],
               "page_role":role, "page_sha256":digest, "size_bytes":len(raw), "paper_id":paper_id}
        page_rows.append(row); page_by_path[path] = row
        input_rows.append({"input_kind":"indexed-page","path":path,"raw_sha256":digest,"size_bytes":len(raw),"runtime_sha256":None})

    compiled_rows=[]
    for i,item in enumerate(compiled):
        if type(item) is not dict or set(item)!={"path","compiler_role","bytes"}:
            _fail("CATALOG_INPUT_INVALID","compiled page descriptor is not closed",f"/compiled_pages/{i}")
        raw=_bytes(item["bytes"],f"/compiled_pages/{i}/bytes"); page=page_by_path.get(item["path"])
        if item["compiler_role"] not in {"paper","code","concept"} or page is None or page["page_sha256"]!=_sha(raw) or page["page_role"]!=item["compiler_role"]:
            _fail("CATALOG_INPUT_INVALID","compiled page is not an exact indexed subset",f"/compiled_pages/{i}")
        compiled_rows.append({"page_path":item["path"],"compiler_role":item["compiler_role"],"page_sha256":_sha(raw)})
    expected_compiled={row["page_path"] for row in page_rows if row["page_role"] in {"paper","code","concept"}}
    if {row["page_path"] for row in compiled_rows}!=expected_compiled:
        _fail("CATALOG_INPUT_INVALID","compiler pages are not the complete non-navigation indexed set","/compiled_pages")

    chunk_rows=[]; chunk_records={}; chunk_paths=set()
    for i,item in enumerate(chunks):
        if type(item) is not dict or set(item)!={"path","bytes","record"}:
            _fail("CATALOG_INPUT_INVALID","chunk descriptor is not closed",f"/chunks/{i}")
        raw=_bytes(item["bytes"],f"/chunks/{i}/bytes"); record=validate_runtime_record("chunk",item["record"])
        runtime=runtime_projection_sha256("chunk",record); chunk_id=f"{record['page_address']}:{record['chunk_index']}"
        expected_path=f".vault-meta/chunks/{record['page_address']}/chunk-{record['chunk_index']:03d}.json"
        if item["path"]!=expected_path or record["page_path"] not in page_by_path or expected_path in chunk_paths:
            _fail("CATALOG_INPUT_INVALID","chunk path/page binding differs",f"/chunks/{i}")
        chunk_paths.add(expected_path); chunk_records[chunk_id]=record
        chunk_rows.append({"chunk_id":chunk_id,"chunk_path":expected_path,"input_kind":"upstream-chunk","page_path":record["page_path"],"page_address":record["page_address"],"chunk_index":record["chunk_index"],"raw_sha256":_sha(raw),"runtime_sha256":runtime,"body_sha256":record["body_hash"].removeprefix("sha256:"),"page_body_sha256":record["page_body_hash"].removeprefix("sha256:"),"document_length":None})
        input_rows.append({"input_kind":"upstream-chunk","path":expected_path,"raw_sha256":_sha(raw),"size_bytes":len(raw),"runtime_sha256":runtime})

    if {row["page_path"] for row in chunk_rows} != set(page_by_path):
        _fail("CATALOG_INPUT_INVALID","indexed pages do not equal the runtime complete set","/indexed_pages")

    if set(bm25)!={"path","bytes","record"}:
        _fail("CATALOG_INPUT_INVALID","BM25 descriptor is not closed","/bm25")
    bmraw=_bytes(bm25["bytes"],"/bm25/bytes"); bmrecord=validate_runtime_record("bm25",bm25["record"])
    docs=bmrecord.get("docs")
    if type(docs) is not dict or set(docs)!=set(chunk_records):
        _fail("CATALOG_INPUT_INVALID","BM25 and chunk complete sets differ","/bm25/record/docs")
    for row in chunk_rows:
        doc=docs[row["chunk_id"]]
        if doc["path"]!=row["chunk_path"] or doc["body_hash"]!="sha256:"+row["body_sha256"] or doc["page_body_hash"]!="sha256:"+row["page_body_sha256"]:
            _fail("CATALOG_INPUT_INVALID","BM25 document binding differs","/bm25/record/docs")
        length=doc.get("dl")
        if type(length) is not int or type(length) is bool or length<0:
            _fail("CATALOG_ROWS_INVALID","document length is not exact nonnegative integer")
        row["document_length"]=length
    bm_runtime=runtime_projection_sha256("bm25",bmrecord)
    input_rows.append({"input_kind":"upstream-bm25","path":bm25["path"],"raw_sha256":_sha(bmraw),"size_bytes":len(bmraw),"runtime_sha256":bm_runtime})
    cfg_raw=retrieval_config_bytes(config)
    input_rows.append({"input_kind":"retrieval-config","path":"retrieval-config.json","raw_sha256":_sha(cfg_raw),"size_bytes":len(cfg_raw),"runtime_sha256":None})

    from video_paper_wiki.evidence_join import join_evidence
    rebuilt=join_evidence(inventory=mapping["inventory"],
        pages={item["path"]:item["bytes"] for item in pages},chunks=chunk_records,bm25=bmrecord)
    if rebuilt!=mapping:
        _fail("RETRIEVAL_GENERATION_MISMATCH","mapping is not the exact derivation from current page/runtime bytes")

    mapped={x["chunk_id"]:x for x in mapping["chunks"]}
    if set(mapped)!=set(chunk_records):
        _fail("CATALOG_ROWS_INVALID","mapping and chunk complete sets differ")
    units=[]
    for unit in mapping["inventory"]["units"]:
        units.append({k:(int(unit[k]) if k in {"core","default_eligible","gold_eligible"} else unit[k]) for k in ("evidence_unit_id","paper_id","claim_id","locator_fingerprint","lifecycle","assessment","core","default_eligible","gold_eligible")})
    chunk_evidence=[]
    for chunk_id in sorted(mapped):
        for ordinal,unit_id in enumerate(mapped[chunk_id]["evidence_unit_ids"]):
            chunk_evidence.append({"chunk_id":chunk_id,"ordinal":ordinal,"evidence_unit_id":unit_id})

    inventory_entries=material["base_generation_material"]["inventory"]["entries"]
    generation={"schema":"video-paper-wiki.search-catalog-generation.v1","profile":PROFILE,
        "base_generation_sha256":base_generation,"base_catalog_rows_sha256":_sha(base_raw),
        "join_generation_sha256":mapping["generation_sha256"],"mapping_sha256":mapping["mapping_sha256"],
        "retrieval_config_sha256":_sha(cfg_raw),"canonical_input_set_sha256":_sha(canonicalize(inventory_entries)),
        "indexed_pages":[{"path":x["page_path"],"role":x["page_role"],"sha256":x["page_sha256"],"size_bytes":x["size_bytes"],"paper_id":x["paper_id"]} for x in page_rows],
        "compiled_pages":[{"path":x["page_path"],"compiler_role":x["compiler_role"],"sha256":x["page_sha256"]} for x in compiled_rows],
        "upstream_chunks":[{"path":x["chunk_path"],"raw_sha256":x["raw_sha256"],"size_bytes":next(y["size_bytes"] for y in input_rows if y["path"]==x["chunk_path"]),"runtime_sha256":x["runtime_sha256"]} for x in chunk_rows],
        "upstream_bm25":{"path":bm25["path"],"raw_sha256":_sha(bmraw),"size_bytes":len(bmraw),"runtime_sha256":bm_runtime},
        "evidence_inventory_sha256":_inventory_digest(mapping["inventory"]),"extension_ddl_sha256":_sha(ddl),
        "extension_manifest_sha256":_sha(_resource("search-catalog-v1.columns.json")),"builder_files":material["builder_files"]}
    validate_document(generation,"video-paper-wiki.search-catalog-generation.v1")
    for key in ("indexed_pages","compiled_pages","upstream_chunks","builder_files"):
        if generation[key] != sorted(generation[key],key=lambda x:x["path"].encode()):
            _fail("CATALOG_INPUT_INVALID","generation collection is not sorted",f"/{key}")
    catalog_generation=_sha(canonicalize(generation))
    meta={"singleton":1,"schema_version":PROFILE,"export_version":"search-catalog-export-v1",
        "join_generation_sha256":mapping["generation_sha256"],"mapping_sha256":mapping["mapping_sha256"],"retrieval_config_sha256":_sha(cfg_raw),"catalog_generation_sha256":catalog_generation,
        "base_generation_sha256":base_generation,"base_catalog_rows_sha256":_sha(base_raw),
        "indexed_page_set_sha256":_sha(canonicalize(generation["indexed_pages"])),"compiled_page_set_sha256":_sha(canonicalize(generation["compiled_pages"])),
        "upstream_chunk_set_sha256":_sha(canonicalize(generation["upstream_chunks"])),"upstream_index_raw_sha256":_sha(bmraw),"upstream_index_runtime_sha256":bm_runtime,
        "evidence_inventory_sha256":generation["evidence_inventory_sha256"],"extension_ddl_sha256":_sha(ddl),"extension_manifest_sha256":generation["extension_manifest_sha256"],"builder_version":"0.1.0"}
    extensions={"search_catalog_meta":[meta],"search_catalog_inputs":input_rows,"search_pages":page_rows,"search_compiled_pages":compiled_rows,"search_chunks":chunk_rows,"search_evidence_units":units,"search_chunk_evidence":chunk_evidence}
    return {"generation":generation,"meta":meta,"extensions":extensions,"base_tables":copy.deepcopy(material["base_tables"]),"mapping":copy.deepcopy(mapping),"config":copy.deepcopy(config)}


def _definitions() -> tuple[list[dict], dict[str, dict]]:
    _ddl, ext, _profile, base = _resources()
    tables=base["tables"]+ext["tables"]
    return tables,{x["name"]:x for x in tables}


def _row_values(definition: dict, rows: list[dict]) -> list[list[Any]]:
    columns=[x["name"] for x in definition["columns"]]
    result=[]
    for ri,row in enumerate(rows):
        if type(row) is not dict or set(row)!=set(columns):_fail("CATALOG_ROWS_INVALID","row keys differ",f"/{definition['name']}/{ri}")
        values=[]
        for col in definition["columns"]:
            value=row[col["name"]]
            if value is not None and ((col["type"]=="INTEGER" and type(value) is not int) or (col["type"]=="TEXT" and type(value) is not str)):
                _fail("CATALOG_ROWS_INVALID","row scalar type differs",f"/{definition['name']}/{ri}/{col['name']}")
            values.append(value)
        result.append(values)
    return result


def _tables_from_prepared(prepared: dict) -> list[dict]:
    definitions,by=_definitions(); base={x["name"]:copy.deepcopy(x) for x in prepared["base_tables"]}
    for name,rows in prepared["extensions"].items():
        definition=by[name];base[name]={"name":name,"columns":[x["name"] for x in definition["columns"]],"rows":_row_values(definition,rows)}
    return [base[x["name"]] for x in definitions]


def canonical_search_catalog_export(prepared: object) -> bytes:
    if type(prepared) is not dict or not {"generation","meta","extensions","base_tables"}<=set(prepared):
        _fail("CATALOG_ROWS_INVALID","prepared catalog shape differs")
    definitions,_=_definitions(); supplied={x["name"]:x for x in _tables_from_prepared(prepared)}; output=[]
    for definition in sorted(definitions,key=lambda x:x["name"].encode()):
        item=supplied[definition["name"]];cols=item["columns"];pk=[cols.index(x) for x in definition["primary_key"]]
        def key(row:list[Any]):return tuple((0,x) if type(x) is int else (1,x.encode()) for x in (row[i] for i in pk))
        output.append({"name":item["name"],"columns":cols,"rows":sorted(item["rows"],key=key)})
    meta=prepared["meta"]
    value={"schema":"video-paper-wiki.search-catalog-export.v1","schema_version":PROFILE,"catalog_generation_sha256":meta["catalog_generation_sha256"],"join_generation_sha256":meta["join_generation_sha256"],"mapping_sha256":meta["mapping_sha256"],"retrieval_config_sha256":meta["retrieval_config_sha256"],"base_catalog_rows_sha256":meta["base_catalog_rows_sha256"],"tables":output}
    validate_document(value,"video-paper-wiki.search-catalog-export.v1")
    return canonicalize(value)


def _insert(connection: sqlite3.Connection, prepared: dict) -> None:
    definitions,_=_definitions(); supplied={x["name"]:x for x in _tables_from_prepared(prepared)}
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(_resource("base-catalog-v1.sql").decode("utf-8"))
    connection.executescript(_resource("search-catalog-v1.sql").decode("utf-8"))
    for definition in definitions:
        item=supplied[definition["name"]];columns=item["columns"]
        sql=f'INSERT INTO "{item["name"]}" ('+",".join(f'"{x}"' for x in columns)+") VALUES ("+",".join("?" for _ in columns)+")"
        connection.executemany(sql,item["rows"])
    bad=connection.execute("PRAGMA foreign_key_check").fetchall()
    if bad:_fail("CATALOG_ROWS_INVALID","catalog foreign keys differ")


def build_catalog_database(path: Path|str, material: object, *, fault: Callable[[str],None]|None=None) -> dict[str,Any]:
    """Build and atomically replace one disposable catalog database."""
    target=Path(path);prepared=prepare_catalog_material(material);expected=canonical_search_catalog_export(prepared)
    from video_paper_wiki.secure_io import open_dir_nofollow,close_fd,stamp
    try:parent_stat=target.parent.lstat()
    except OSError:_fail("CATALOG_BUILD_RACE","catalog parent is unavailable")
    if not stat.S_ISDIR(parent_stat.st_mode) or stat.S_ISLNK(parent_stat.st_mode):_fail("CATALOG_BUILD_RACE","catalog parent is unsafe")
    parent_fd=open_dir_nofollow(target.parent,missing_code="CATALOG_BUILD_RACE",unsafe_code="CATALOG_BUILD_RACE")
    parent_identity=(parent_stat.st_dev,parent_stat.st_ino,stat.S_IMODE(parent_stat.st_mode))
    def verify_parent():
        try:named=target.parent.lstat();held=os.fstat(parent_fd)
        except OSError:_fail("CATALOG_BUILD_RACE","catalog parent changed")
        if (named.st_dev,named.st_ino,stat.S_IMODE(named.st_mode))!=parent_identity or (held.st_dev,held.st_ino,stat.S_IMODE(held.st_mode))!=parent_identity:_fail("CATALOG_BUILD_RACE","catalog parent changed")
    old_held=_RetainedFile(target,required=False)
    if old_held.fd is None:old=None
    else:
        os.lseek(old_held.fd,0,os.SEEK_SET);old=b""
        while True:
            part=os.read(old_held.fd,1024*1024)
            if not part:break
            old+=part
        old_held.verify_edge("CATALOG_BUILD_RACE")
    import secrets
    tmp_name=f".catalog-{secrets.token_hex(12)}.sqlite"
    flags=os.O_RDWR|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
    activated=False;installed_held=None
    try:
        con=sqlite3.connect(":memory:")
        try:
            _insert(con,prepared)
            if fault:fault("before-commit")
            con.commit()
            if con.execute("PRAGMA quick_check").fetchone()!=("ok",) or con.execute("PRAGMA integrity_check").fetchone()!=("ok",):_fail("CATALOG_ROWS_INVALID","SQLite integrity differs")
            database_bytes=con.serialize()
        finally:con.close()
        if len(database_bytes)>MAX_SOURCE:_fail("CATALOG_ROWS_INVALID","serialized catalog exceeds byte limit")
        fd=os.open(tmp_name,flags,0o600,dir_fd=parent_fd)
        try:
            view=memoryview(database_bytes)
            while view:view=view[os.write(fd,view):]
            os.fsync(fd)
            written=os.fstat(fd);named=os.stat(tmp_name,dir_fd=parent_fd,follow_symlinks=False)
            if stamp(written)!=stamp(named):_fail("CATALOG_BUILD_RACE","catalog temporary file changed")
        finally:os.close(fd)
        verify_parent();old_held.verify_edge("CATALOG_BUILD_RACE")
        if fault:fault("before-replace")
        verify_parent();old_held.verify_edge("CATALOG_BUILD_RACE")
        os.rename(tmp_name,target.name,src_dir_fd=parent_fd,dst_dir_fd=parent_fd);activated=True
        if fault:fault("after-activation-rename")
        installed_held=_RetainedFile(target)
        verify_parent()
        if fault:fault("before-parent-fsync")
        os.fsync(parent_fd)
        if fault:fault("after-replace")
        try:
            observed=canonical_export_from_database(target,_held=installed_held)
            installed_held.verify("CATALOG_BUILD_RACE")
            if observed!=expected:_fail("CATALOG_ROWS_INVALID","read-back canonical export differs")
        finally:installed_held.close();installed_held=None
        return {"database":DB_RELATIVE,"catalog_generation_sha256":prepared["meta"]["catalog_generation_sha256"],"export_sha256":_sha(expected),"digests":{k:prepared["meta"][k] for k in ("join_generation_sha256","mapping_sha256","retrieval_config_sha256","catalog_generation_sha256")}}
    except ContractError:
        if activated:
            try:
                if fault:fault("before-rollback")
                if installed_held is None:_fail("CATALOG_RECOVERY_REQUIRED","activated catalog identity was not retained")
                installed_held.verify_edge("CATALOG_RECOVERY_REQUIRED")
                if old is None:
                    tomb=f".catalog-rejected-{secrets.token_hex(12)}";os.rename(target.name,tomb,src_dir_fd=parent_fd,dst_dir_fd=parent_fd)
                    named=os.stat(tomb,dir_fd=parent_fd,follow_symlinks=False)
                    if (named.st_dev,named.st_ino)!=(installed_held.file_stat.st_dev,installed_held.file_stat.st_ino):_fail("CATALOG_RECOVERY_REQUIRED","catalog rollback target changed")
                    os.unlink(tomb,dir_fd=parent_fd)
                else:
                    recovery_name=f".catalog-rollback-{secrets.token_hex(12)}";rfd=os.open(recovery_name,flags,0o600,dir_fd=parent_fd)
                    try:
                        view=memoryview(old)
                        while view:view=view[os.write(rfd,view):]
                        os.fsync(rfd)
                    finally:os.close(rfd)
                    os.rename(recovery_name,target.name,src_dir_fd=parent_fd,dst_dir_fd=parent_fd)
                os.fsync(parent_fd);verify_parent()
                if old is not None:
                    restored=_RetainedFile(target)
                    try:
                        os.lseek(restored.fd,0,os.SEEK_SET);seen=b""
                        while True:
                            part=os.read(restored.fd,1024*1024)
                            if not part:break
                            seen+=part
                        if seen!=old:_fail("CATALOG_RECOVERY_REQUIRED","catalog rollback differs")
                        restored.verify("CATALOG_RECOVERY_REQUIRED")
                    finally:restored.close()
            except OSError:_fail("CATALOG_RECOVERY_REQUIRED","catalog rollback cannot be proven")
        raise
    except BaseException:
        if activated:
            try:
                if fault:fault("before-rollback")
                if installed_held is None:_fail("CATALOG_RECOVERY_REQUIRED","activated catalog identity was not retained")
                installed_held.verify_edge("CATALOG_RECOVERY_REQUIRED")
                if old is None:
                    tomb=f".catalog-rejected-{secrets.token_hex(12)}";os.rename(target.name,tomb,src_dir_fd=parent_fd,dst_dir_fd=parent_fd)
                    named=os.stat(tomb,dir_fd=parent_fd,follow_symlinks=False)
                    if (named.st_dev,named.st_ino)!=(installed_held.file_stat.st_dev,installed_held.file_stat.st_ino):_fail("CATALOG_RECOVERY_REQUIRED","catalog rollback target changed")
                    os.unlink(tomb,dir_fd=parent_fd)
                else:
                    recovery_name=f".catalog-rollback-{secrets.token_hex(12)}";rfd=os.open(recovery_name,flags,0o600,dir_fd=parent_fd)
                    try:
                        view=memoryview(old)
                        while view:view=view[os.write(rfd,view):]
                        os.fsync(rfd)
                    finally:os.close(rfd)
                    os.rename(recovery_name,target.name,src_dir_fd=parent_fd,dst_dir_fd=parent_fd)
                os.fsync(parent_fd);verify_parent()
                if old is not None:
                    restored=_RetainedFile(target)
                    try:
                        os.lseek(restored.fd,0,os.SEEK_SET);seen=b""
                        while True:
                            part=os.read(restored.fd,1024*1024)
                            if not part:break
                            seen+=part
                        if seen!=old:_fail("CATALOG_RECOVERY_REQUIRED","catalog rollback differs")
                        restored.verify("CATALOG_RECOVERY_REQUIRED")
                    finally:restored.close()
            except OSError:_fail("CATALOG_RECOVERY_REQUIRED","catalog rollback cannot be proven")
        _fail("CATALOG_BUILD_FAILED","catalog build failed")
    finally:
        try:os.unlink(tmp_name,dir_fd=parent_fd)
        except FileNotFoundError:pass
        if installed_held is not None:installed_held.close()
        old_held.close();close_fd(parent_fd)


def _readonly(path: Path,held:_RetainedFile|None=None) -> sqlite3.Connection:
    owned=held is None
    try:
        if held is None:held=_RetainedFile(path)
        assert held.fd is not None;os.lseek(held.fd,0,os.SEEK_SET);parts=[];total=0
        while True:
            part=os.read(held.fd,1024*1024)
            if not part:break
            total+=len(part)
            if total>MAX_SOURCE:_fail("CATALOG_STALE","catalog database exceeds byte limit")
            parts.append(part)
        held.verify();con=sqlite3.connect(":memory:");con.deserialize(b"".join(parts))
        con.execute("PRAGMA query_only=ON")
        return con
    except sqlite3.Error:_fail("CATALOG_STALE","catalog database is unavailable")
    finally:
        if owned and held is not None:held.close()


def canonical_export_from_database(path: Path|str,*,_held:_RetainedFile|None=None) -> bytes:
    con=_readonly(Path(path),_held)
    try:
        definitions,_=_definitions();tables=[]
        for definition in definitions:
            cols=[x["name"] for x in definition["columns"]];order=definition["primary_key"]
            sql=f'SELECT '+",".join(f'"{x}"' for x in cols)+f' FROM "{definition["name"]}"'
            if order:sql+=' ORDER BY '+",".join(f'"{x}" COLLATE BINARY' if next(c for c in definition["columns"] if c["name"]==x)["type"]=="TEXT" else f'"{x}"' for x in order)
            tables.append({"name":definition["name"],"columns":cols,"rows":[list(x) for x in con.execute(sql)]})
        meta=dict(zip([x[1] for x in con.execute("PRAGMA table_info(search_catalog_meta)")],con.execute("SELECT * FROM search_catalog_meta").fetchone()))
        value={"schema":"video-paper-wiki.search-catalog-export.v1","schema_version":PROFILE,"catalog_generation_sha256":meta["catalog_generation_sha256"],"join_generation_sha256":meta["join_generation_sha256"],"mapping_sha256":meta["mapping_sha256"],"retrieval_config_sha256":meta["retrieval_config_sha256"],"base_catalog_rows_sha256":meta["base_catalog_rows_sha256"],"tables":sorted(tables,key=lambda x:x["name"].encode())}
        validate_document(value,"video-paper-wiki.search-catalog-export.v1");return canonicalize(value)
    except (sqlite3.Error,TypeError,KeyError):_fail("CATALOG_STALE","catalog database does not match the frozen schema")
    finally:con.close()


def _config(value: object,*,allow_policy:bool=False) -> tuple[dict,bytes]:
    try:
        if isinstance(value,(str,Path)):
            doc=load_strict_json(Path(value),missing_code="CATALOG_STALE",unsafe_code="CATALOG_STALE",invalid_code="CATALOG_STALE",changed_code="CATALOG_STALE",max_bytes=1_048_576)
        else:doc=copy.deepcopy(value)
        if type(doc) is not dict or doc.get("schema") not in ({"video-paper-wiki.retrieval-config.v1","video-paper-wiki.retrieval-policy.v1"} if allow_policy else {"video-paper-wiki.retrieval-config.v1"}):raise ValueError
        cfg=validate_retrieval_policy(doc) if doc["schema"]=="video-paper-wiki.retrieval-policy.v1" else validate_retrieval_config(doc)
        return copy.deepcopy(cfg),canonicalize(cfg)
    except (ContractError,ValueError,TypeError) as exc:
        raise ContractError("CATALOG_STALE","retrieval policy or config is invalid",{}) from exc


def _retained_config(value:object)->tuple[dict,bytes,_RetainedFile|None]:
    if not isinstance(value,(str,Path)):
        cfg,raw=_config(value);return cfg,raw,None
    held=_RetainedFile(Path(value))
    try:
        assert held.fd is not None;os.lseek(held.fd,0,os.SEEK_SET);raw=os.read(held.fd,1_048_577)
        if len(raw)>1_048_576:_fail("CATALOG_STALE","retrieval config exceeds limit")
        from video_paper_wiki.secure_io import parse_strict_json
        cfg=validate_retrieval_config(parse_strict_json(raw,invalid_code="CATALOG_STALE"));held.verify();return cfg,canonicalize(cfg),held
    except BaseException:
        held.close();raise


def _meta(con:sqlite3.Connection)->dict[str,Any]:
    cols=[x[1] for x in con.execute("PRAGMA table_info(search_catalog_meta)")];rows=con.execute("SELECT * FROM search_catalog_meta").fetchall()
    if len(rows)!=1:_fail("CATALOG_STALE","catalog metadata is missing or duplicated")
    return dict(zip(cols,rows[0]))


def catalog_status(vault_root:Path|str,upstream_root:Path|str,retrieval_config:object,*,
                   _collector:Callable[...,object]|None=None,barrier:Callable[[str],None]|None=None,
                   _config_material:tuple[dict,bytes,_RetainedFile|None]|None=None,
                   _live_holder:list[Any]|None=None)->dict[str,Any]:
    upstream=verify_upstream(upstream_root);owned_config=_config_material is None
    cfg,raw,config_held=_retained_config(retrieval_config) if owned_config else _config_material
    path=Path(vault_root)/DB_RELATIVE;held=None;live_snap=None;default_collector=_collector is None
    if _collector is None:
        from video_paper_wiki.catalog_collector import collect_current_catalog_material
        _collector=collect_current_catalog_material
    try:
        held=_RetainedFile(path)
        con=_readonly(path,held)
        try:
            meta=_meta(con);canonical_export_from_database(path,_held=held)
        finally:con.close()
        try:
            collected=_collector(vault_root=Path(vault_root),upstream_root=upstream,retrieval_config=cfg,**({"_retain":True} if default_collector else {}))
        except ContractError as exc:
            raise ContractError("CATALOG_STALE","live catalog authority is invalid",{}) from exc
        if default_collector and type(collected) is tuple and len(collected)==2:
            material,live_snap=collected
        else:material=collected
        live=prepare_catalog_material(material)["meta"]
        if barrier:barrier("before-reader-recheck")
        held.verify();
        if live_snap:live_snap.verify()
        if config_held:config_held.verify()
        reasons=[]
        if meta["retrieval_config_sha256"]!=_sha(raw):reasons.append("retrieval-config-changed")
        if meta["join_generation_sha256"]!=cfg["generation_sha256"]:reasons.append("join-generation-changed")
        if meta["mapping_sha256"]!=cfg["mapping_sha256"]:reasons.append("mapping-changed")
        for key,reason in (("join_generation_sha256","live-index-changed"),("mapping_sha256","live-mapping-changed"),("catalog_generation_sha256","live-catalog-changed"),("base_catalog_rows_sha256","live-base-rows-changed")):
            if meta[key]!=live[key]:reasons.append(reason)
        return {"state":"current" if not reasons else "stale","reasons":sorted(reasons),**{k:meta[k] for k in ("join_generation_sha256","mapping_sha256","retrieval_config_sha256","catalog_generation_sha256")}}
    except ContractError:
        if held:held.verify();
        if live_snap:live_snap.verify()
        if config_held:config_held.verify()
        raise
    except OSError:
        if held:held.verify()
        if config_held:config_held.verify()
        _fail("CATALOG_STALE","catalog database is unavailable")
    finally:
        if held:held.close()
        if live_snap:
            if _live_holder is not None:_live_holder.append(live_snap)
            else:live_snap.close()
        if owned_config and config_held:config_held.close()


def mapping_from_database(con:sqlite3.Connection,meta:dict[str,Any])->dict[str,Any]:
    units=[]
    for row in con.execute("SELECT evidence_unit_id,paper_id,claim_id,locator_fingerprint,lifecycle,assessment,core,default_eligible,gold_eligible FROM search_evidence_units ORDER BY evidence_unit_id"):
        unit=dict(zip(("evidence_unit_id","paper_id","claim_id","locator_fingerprint","lifecycle","assessment","core","default_eligible","gold_eligible"),row));unit.update({"core":bool(unit["core"]),"default_eligible":bool(unit["default_eligible"]),"gold_eligible":bool(unit["gold_eligible"])})
        # Locator is intentionally not stored in the extension; reconstruct it
        # from the canonical base claim_evidence row by fingerprint.
        candidates=[]
        from video_paper_wiki.ledger_locator import decode_ledger_evidence
        from video_paper_wiki.identity import locator_fingerprint
        for source_id,relation,wire in con.execute("SELECT source_id,wire_relation,locator_wire FROM claim_evidence WHERE claim_id=? ORDER BY ordinal",(unit["claim_id"],)):
            candidate=decode_ledger_evidence({"relation":relation,"source_id":source_id,"locator":wire})
            if locator_fingerprint(candidate)==unit["locator_fingerprint"]:candidates.append(candidate)
        if len(candidates)!=1:_fail("CATALOG_STALE","evidence locator cannot be reconstructed")
        unit["locator"]=candidates[0];units.append(unit)
    chunks=[]
    for row in con.execute("SELECT chunk_id,chunk_path,body_sha256,page_body_sha256,page_path FROM search_chunks ORDER BY chunk_id"):
        cid,path,body,page_body,page_path=row
        ids=[x[0] for x in con.execute("SELECT evidence_unit_id FROM search_chunk_evidence WHERE chunk_id=? ORDER BY ordinal",(cid,))]
        owners={con.execute("SELECT paper_id FROM search_evidence_units WHERE evidence_unit_id=?",(x,)).fetchone()[0] for x in ids}
        if len(owners)>1:_fail("CATALOG_STALE","chunk evidence has multiple owners")
        owner=next(iter(owners),None)
        defaults=[x for x in ids if con.execute("SELECT default_eligible FROM search_evidence_units WHERE evidence_unit_id=?",(x,)).fetchone()[0]]
        chunks.append({"chunk_id":cid,"path":path,"body_hash":"sha256:"+body,"page_body_hash":"sha256:"+page_body,"paper_id":owner,"evidence_unit_ids":ids,"default_evidence_unit_ids":defaults})
    mapping={"schema":"video-paper-wiki.evidence-mapping-authority.v1","profile":"claude-obsidian.chunk-v1+bm25-v2","generation_sha256":meta["join_generation_sha256"],"inventory":{"schema":"video-paper-wiki.evidence-inventory.v1","units":units},"chunks":chunks,"mapping_sha256":meta["mapping_sha256"]}
    return validate_evidence_mapping_authority(mapping)


def query_catalog(vault_root:Path|str,upstream_root:Path|str,retrieval_config:object,text:str,*,
                  _collector:Callable[...,object]|None=None,barrier:Callable[[str],None]|None=None)->dict[str,Any]:
    cfg,raw,config_held=_retained_config(retrieval_config)
    live=[]
    try:
        status=catalog_status(vault_root,upstream_root,retrieval_config,_collector=_collector,_config_material=(cfg,raw,config_held),_live_holder=live)
        if status["state"]!="current":_fail("CATALOG_STALE","catalog is stale")
        path=Path(vault_root)/DB_RELATIVE;held=_RetainedFile(path)
        try:
            con=_readonly(path,held)
            try:
                con.execute("BEGIN");meta=_meta(con);mapping=mapping_from_database(con,meta)
                script_held=_RetainedFile(Path(upstream_root)/"scripts/bm25-index.py")
                try:
                    raw_hits=bm25_query(vault_root=vault_root,upstream_root=upstream_root,text=text,top=cfg["top_chunks"])
                    script_held.verify("RETRIEVAL_GENERATION_MISMATCH")
                finally:script_held.close()
                ranked=rank_hits(raw_hits,mapping,cfg);con.execute("COMMIT")
            except ContractError as exc:
                raise ContractError("RETRIEVAL_GENERATION_MISMATCH","catalog query inputs differ",exc.details) from None
            finally:con.close()
            if barrier:barrier("after-query-child")
            for snapshot in live:snapshot.verify()
            held.verify("RETRIEVAL_GENERATION_MISMATCH")
            if config_held:config_held.verify("RETRIEVAL_GENERATION_MISMATCH")
            final=catalog_status(vault_root,upstream_root,retrieval_config,_collector=_collector,_config_material=(cfg,raw,config_held))
            if final["state"]!="current" or any(final[k]!=status[k] for k in ("join_generation_sha256","mapping_sha256","retrieval_config_sha256","catalog_generation_sha256")):_fail("RETRIEVAL_GENERATION_MISMATCH","catalog authority changed during query")
            return {"raw_hits":copy.deepcopy(raw_hits),"ranking":ranked,**{k:meta[k] for k in ("join_generation_sha256","mapping_sha256","retrieval_config_sha256","catalog_generation_sha256")}}
        finally:
            try:held.verify("RETRIEVAL_GENERATION_MISMATCH")
            finally:held.close()
    finally:
        for snapshot in live:
            try:snapshot.verify()
            finally:snapshot.close()
        if config_held:
            try:config_held.verify("RETRIEVAL_GENERATION_MISMATCH")
            finally:config_held.close()


__all__=["DB_RELATIVE","LOCK_RELATIVE","prepare_catalog_material","canonical_search_catalog_export","build_catalog_database","canonical_export_from_database","catalog_status","mapping_from_database","query_catalog"]


def _git_identity(upstream:Path)->tuple[str,str]:
    env={"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null","GIT_NO_LAZY_FETCH":"1"}
    def read(*args:str)->str:
        try:
            result=subprocess.run(["git","--no-optional-locks","--no-replace-objects","-c","core.fsmonitor=false","-C",str(upstream),*args],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
        except (OSError,subprocess.TimeoutExpired):_fail("CATALOG_BUILD_RACE","upstream Git authority is unavailable")
        if result.returncode or len(result.stdout)>4096 or len(result.stderr)>4096:_fail("CATALOG_BUILD_RACE","upstream Git authority differs")
        try:return result.stdout.decode("ascii").strip()
        except UnicodeError:_fail("CATALOG_BUILD_RACE","upstream Git authority differs")
    head=read("rev-parse","HEAD");tree=read("rev-parse","HEAD^{tree}")
    if len(head)!=40 or len(tree)!=40 or any(c not in _HEX for c in head+tree):_fail("CATALOG_BUILD_RACE","upstream Git authority differs")
    return head,tree


def _git_blob(upstream:Path,commit:str,relative:str)->bytes:
    env={"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null","GIT_NO_LAZY_FETCH":"1"}
    if len(commit)!=40 or any(c not in _HEX for c in commit):_fail("CATALOG_BUILD_RACE","upstream builder commit differs")
    try:result=subprocess.run(["git","--no-optional-locks","--no-replace-objects","-c","core.fsmonitor=false","-C",str(upstream),"show",f"{commit}:{relative}"],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
    except (OSError,subprocess.TimeoutExpired):_fail("CATALOG_BUILD_RACE","upstream builder source is unavailable")
    if result.returncode or len(result.stdout)>2*1024*1024 or len(result.stderr)>4096:_fail("CATALOG_BUILD_RACE","upstream builder source differs")
    return result.stdout


def _run_builders(vault:Path,upstream:Path,observer:Callable[[str],None]|None=None)->None:
    from video_paper_wiki.upstream_adapter import _authenticate,_cleanup,_make_allocation,_profile,_verify_allocation
    _raw,profile=_profile();expected_git=_git_identity(upstream);sources=_authenticate(upstream,profile)
    sources={**sources,**{path:_git_blob(upstream,expected_git[0],path) for path in ("scripts/contextual-prefix.py","scripts/bm25-index.py")}}
    if expected_git!=(profile["git_commit"],profile["git_tree"]):_fail("CATALOG_BUILD_RACE","upstream Git authority differs")
    allocation=_make_allocation(sources,(vault,upstream))
    try:
        scratch=allocation.scratch;execution=allocation.execution;env={k:str(scratch) for k in ("HOME","TEMP","TMP","TMPDIR")}
        commands=(
            [sys.executable,"-I","-B","-X","utf8",str(execution/"scripts/contextual-prefix.py"),"--vault",str(vault),"--all","--no-llm"],
            [sys.executable,"-I","-B","-X","utf8",str(execution/"scripts/bm25-index.py"),"--vault",str(vault),"build"],
        )
        def verify_all()->None:
            _verify_allocation(allocation,sources,code="CATALOG_BUILD_RACE")
            if _git_identity(upstream)!=expected_git:_fail("CATALOG_BUILD_RACE","upstream Git authority changed")
        try:
            for index,command in enumerate(commands):
                verify_all()
                if observer:observer("prefix" if index==0 else "bm25")
                try:result=subprocess.run(command,cwd=execution,env=env,input=b"",stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300,check=False)
                except (OSError,subprocess.TimeoutExpired):_fail("CATALOG_BUILD_FAILED","pinned catalog builder failed")
                verify_all()
                if result.returncode or len(result.stdout)>16*1024*1024 or len(result.stderr)>16*1024*1024:_fail("CATALOG_BUILD_FAILED","pinned catalog builder refused")
        finally:
            verify_all()
    finally:_cleanup(allocation)


def _build_current_catalog_core(*,vault_root:Path|str,upstream_root:Path|str,retrieval_config:object,_collector:Callable[...,object]|None=None,fault:Callable[[str],None]|None=None,child_observer:Callable[[str],None]|None=None)->dict[str,Any]:
    """Operator-only writer.  The CLI supplies the interactive authority."""
    from video_paper_wiki.secure_io import close_fd,dir_open_flags,lexical_abs,open_dir_nofollow,stamp
    vault=lexical_abs(vault_root);upstream=verify_upstream(upstream_root);cfg,_cfgraw=_config(retrieval_config,allow_policy=True)
    policy=cfg if cfg.get("schema")=="video-paper-wiki.retrieval-policy.v1" else None
    root_fd=open_dir_nofollow(vault,missing_code="CATALOG_BUILD_RACE",unsafe_code="CATALOG_BUILD_RACE")
    root_stat=os.fstat(root_fd)
    try:meta_fd=os.open(".vault-meta",dir_open_flags(),dir_fd=root_fd)
    except OSError:close_fd(root_fd);_fail("CATALOG_BUILD_RACE","catalog metadata directory is unsafe")
    try:
        try:os.mkdir("locks",0o700,dir_fd=meta_fd)
        except FileExistsError:pass
        locks_fd=os.open("locks",dir_open_flags(),dir_fd=meta_fd)
    except OSError:close_fd(meta_fd);close_fd(root_fd);_fail("CATALOG_BUILD_RACE","catalog lock directory is unsafe")
    locks=vault/".vault-meta/locks";lock=locks/"catalog-build.lock";meta_stat=os.fstat(meta_fd)
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
    if hasattr(os,"O_CLOEXEC"):flags|=os.O_CLOEXEC
    try:lock_fd=os.open("catalog-build.lock",flags,0o600,dir_fd=locks_fd)
    except FileExistsError:
        close_fd(locks_fd);close_fd(meta_fd);close_fd(root_fd);_fail("CATALOG_BUILD_BUSY","catalog builder lock is busy")
    except OSError:
        close_fd(locks_fd);close_fd(meta_fd);close_fd(root_fd);_fail("CATALOG_BUILD_RACE","catalog builder lock is unsafe")
    lock_stat=os.fstat(lock_fd)
    locks_stat=os.fstat(locks_fd)
    def same_dir(fd,first):
        current=os.fstat(fd);return (current.st_dev,current.st_ino,stat.S_IMODE(current.st_mode))==(first.st_dev,first.st_ino,stat.S_IMODE(first.st_mode))
    try:
        if fault:fault("after-lock")
        if not same_dir(meta_fd,meta_stat) or not same_dir(locks_fd,locks_stat):_fail("CATALOG_BUILD_RACE","catalog lock lineage changed")
        _run_builders(vault,upstream,child_observer)
        if _collector is None:
            from video_paper_wiki.catalog_collector import collect_current_catalog_material
            _collector=collect_current_catalog_material
        material=_collector(vault_root=vault,upstream_root=upstream,retrieval_config=cfg)
        if policy is not None:
            mapping=material["mapping"]
            cfg=derive_retrieval_config(policy,generation_sha256=mapping["generation_sha256"],mapping_sha256=mapping["mapping_sha256"])
            material={**material,"config":cfg}
        try:named=os.stat("catalog-build.lock",dir_fd=locks_fd,follow_symlinks=False)
        except OSError:_fail("CATALOG_BUILD_RACE","catalog builder lock changed")
        if (named.st_dev,named.st_ino,named.st_mode)!=(lock_stat.st_dev,lock_stat.st_ino,lock_stat.st_mode):_fail("CATALOG_BUILD_RACE","catalog builder lock changed")
        result=build_catalog_database(vault/DB_RELATIVE,material,fault=fault)
        result={**result,"retrieval_config":cfg,"retrieval_config_sha256":_sha(canonicalize(cfg))}
        if not same_dir(meta_fd,meta_stat) or not same_dir(locks_fd,locks_stat):_fail("CATALOG_BUILD_RACE","catalog lock lineage changed")
        return result
    finally:
        try:
            if not same_dir(root_fd,root_stat) or not same_dir(meta_fd,meta_stat) or not same_dir(locks_fd,locks_stat):
                _fail("CATALOG_BUILD_RACE","catalog lock lineage changed")
            tomb=f".catalog-build-owned-{secrets.token_hex(12)}"
            os.rename("catalog-build.lock",tomb,src_dir_fd=locks_fd,dst_dir_fd=locks_fd)
            if fault:fault("after-lock-tombstone")
            try:os.stat("catalog-build.lock",dir_fd=locks_fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:_fail("CATALOG_BUILD_RACE","foreign catalog builder lock appeared during cleanup")
            named=os.stat(tomb,dir_fd=locks_fd,follow_symlinks=False)
            if (named.st_dev,named.st_ino,stat.S_IMODE(named.st_mode))!=(lock_stat.st_dev,lock_stat.st_ino,stat.S_IMODE(lock_stat.st_mode)):
                try:os.link(tomb,"catalog-build.lock",src_dir_fd=locks_fd,dst_dir_fd=locks_fd,follow_symlinks=False)
                except FileExistsError:_fail("CATALOG_BUILD_RACE","foreign catalog builder locks were preserved")
                os.unlink(tomb,dir_fd=locks_fd)
                _fail("CATALOG_BUILD_RACE","catalog builder lock changed")
            os.unlink(tomb,dir_fd=locks_fd);os.fsync(locks_fd)
        except ContractError:raise
        except FileNotFoundError:_fail("CATALOG_BUILD_RACE","catalog builder lock disappeared")
        except OSError:_fail("CATALOG_BUILD_RACE","catalog builder lock cleanup failed")
        finally:
            os.close(lock_fd);close_fd(locks_fd);close_fd(meta_fd);close_fd(root_fd)

def build_current_catalog(*,vault_root:Path|str,upstream_root:Path|str,retrieval_config:object,
        _collector:Callable[...,object]|None=None,fault:Callable[[str],None]|None=None,
        child_observer:Callable[[str],None]|None=None)->dict[str,Any]:
    held=None
    try:
        if isinstance(retrieval_config,(str,Path)):
            from video_paper_wiki.secure_io import parse_strict_json
            try:held=_RetainedFile(Path(retrieval_config))
            except ContractError as exc:raise ContractError("CATALOG_STALE","retrieval policy or config is unsafe",{}) from exc
            try:
                assert held.fd is not None;os.lseek(held.fd,0,os.SEEK_SET);raw=os.read(held.fd,1_048_577)
                if len(raw)>1_048_576:_fail("CATALOG_STALE","retrieval policy or config exceeds limit")
                value=parse_strict_json(raw,invalid_code="CATALOG_STALE")
            except (OSError,ContractError) as exc:raise ContractError("CATALOG_STALE","retrieval policy or config is invalid",{}) from exc
        else:value=copy.deepcopy(retrieval_config)
        cfg,_raw=_config(value,allow_policy=True)
        result=_build_current_catalog_core(vault_root=vault_root,upstream_root=upstream_root,retrieval_config=cfg,
            _collector=_collector,fault=fault,child_observer=child_observer)
        if held is not None:held.verify_edge("CATALOG_STALE")
        expected={"database","catalog_generation_sha256","export_sha256","digests","retrieval_config","retrieval_config_sha256"}
        if set(result)!=expected or result["retrieval_config_sha256"]!=_sha(canonicalize(result["retrieval_config"])) or result["retrieval_config_sha256"]!=result["digests"]["retrieval_config_sha256"] or result["catalog_generation_sha256"]!=result["digests"]["catalog_generation_sha256"]:
            _fail("CATALOG_BUILD_FAILED","catalog build result differs")
        return result
    except BaseException:
        if held is not None:held.verify_edge("CATALOG_STALE")
        raise
    finally:
        if held is not None:held.close()

__all__.extend(["build_current_catalog"])
