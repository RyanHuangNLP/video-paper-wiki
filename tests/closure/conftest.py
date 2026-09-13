from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from video_paper_wiki.backup_archive import create_backup_archive
from video_paper_wiki.backup_manifest import build_backup_manifest
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize


def _put(root: Path, relative: str, data: bytes) -> None:
    target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)


@pytest.fixture
def closure_backup(tmp_path: Path):
    source=tmp_path/'source';source.mkdir();source.chmod(0o700)
    raw=b'closure-pdf';raw_sha=hashlib.sha256(raw).hexdigest();raw_path=f'.raw/captured/{raw_sha}.pdf'
    page=b'closure-page';page_path='wiki/papers/closure.md'
    receipt={'schema':'video-paper-wiki.operation-receipt.v1','sequence':1,'previous':None,
        'operation_id':'closure-genesis','operation_type':'generic','intent_sha256':'0'*64,
        'writes':[{'path':page_path,'mode':'create','before_sha256':None,'after_sha256':hashlib.sha256(page).hexdigest()}],
        'claimed_inputs':[{'path':raw_path,'mode':'read','sha256':raw_sha}]}
    receipt['intent_sha256']=receipt_intent_sha256(receipt);receipt_raw=canonicalize(receipt)
    receipt_path='wiki/meta/operations/000000000001-closure-genesis.json'
    head={'schema':'video-paper-wiki.operation-head.v1','sequence':1,'receipt_path':receipt_path,
        'receipt_sha256':hashlib.sha256(receipt_raw).hexdigest()}
    for path,data in ((raw_path,raw),(page_path,page),(receipt_path,receipt_raw),
            ('wiki/meta/registries/operation-head.json',canonicalize(head))):_put(source,path,data)
    for path in source.rglob('*'):path.chmod(0o700 if path.is_dir() else 0o600)
    manifest=build_backup_manifest(source);archive=tmp_path/'backup.zip'
    create_backup_archive(vault_root=source,manifest=manifest,destination=archive)
    return source,manifest,archive
