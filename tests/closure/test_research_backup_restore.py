from __future__ import annotations

import hashlib
import json
import os
import pty
import stat
import subprocess
from pathlib import Path

import pytest

from video_paper_wiki.article_revision import article_history, status_article_store
from video_paper_wiki.catalog_store import build_current_catalog
from video_paper_wiki.cli import main
from video_paper_wiki.code_proof_public import status_code_proof
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.domain_store import status_domain_store
from video_paper_wiki.experiment_store import status_experiment_store
from video_paper_wiki.flow.status import build_flow_status
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.restore_verification import _research_reads
from video_paper_wiki.staging import StagingError, resolve_checkout_root, validate_batch_id
from video_paper_wiki.upstream_runtime import lint_vault

from tests.closure._p3_recovery_fixture import prepare_research_sources

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.retrieval-policy.v1.json"
UPSTREAM = ROOT / "vendor/claude-obsidian"


def _git(restore: Path, *args: str, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "safe.directory=*", *args],
        cwd=restore,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def _operator(argv: list[str], confirm: bytes, cwd: Path) -> tuple[int, bytes]:
    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, cwd=cwd, stdin=slave, stdout=subprocess.PIPE, stderr=slave)
    os.close(slave)
    os.write(master, confirm)
    try:
        stdout, _stderr = proc.communicate(timeout=240)
    finally:
        os.close(master)
    return proc.returncode, stdout


def _admin(cwd: Path, *args: str) -> list[str]:
    code = (
        "import sys\n"
        "sys.path.insert(0, 'operator/src')\n"
        "from video_paper_wiki_operator.cli import main\n"
        "raise SystemExit(main(sys.argv[1:]))\n"
    )
    return [os.environ.get("PYTHON", "") or __import__("sys").executable, "-c", code, *args]


_RULE_DIRS = {
    "code-evidence-v1",
    "flow",
    "domain",
    "experiments",
    "articles",
    "draft",
    "review",
    "plan",
}


def _whitelist(relative: str) -> bool:
    if relative in {".raw", "wiki", ".work"} or relative.startswith((".raw/", "wiki/")):
        return True
    parts = relative.split("/")
    if not parts or parts[0] != ".work" or len(parts) < 2:
        return False
    if parts[1] in {"blobs", "pdf-migration", "research"}:
        return False
    try:
        validate_batch_id(parts[1])
    except StagingError:
        return False
    return len(parts) == 2 or parts[2] in _RULE_DIRS


def _observe(root: Path) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        found[relative] = {
            "kind": "dir" if stat.S_ISDIR(info.st_mode) else "file",
            "mode": stat.S_IMODE(info.st_mode),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else "",
        }
    return found


def _covered(root: Path, manifest: dict) -> dict[str, tuple[str, int]]:
    found = {}
    for row in manifest["files"]:
        path = root / row["path"]
        found[row["path"]] = (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            stat.S_IMODE(path.stat().st_mode),
        )
    for row in manifest["directories"]:
        path = root / row["path"]
        found[row["path"] + "/"] = ("", stat.S_IMODE(path.stat().st_mode))
    return found


def _cli_data(capsys: pytest.CaptureFixture[str], args: list[str]) -> dict:
    assert main(args) == 0, capsys.readouterr().out
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    return payload["data"]


def test_historical_fixture_keeps_the_reading_lint_failure(tmp_path: Path, monkeypatch) -> None:
    """The rich fixture still fails strict lint. That evidence is not a success-path requirement."""
    prepared = prepare_research_sources(tmp_path, monkeypatch)
    counts = prepared["lint_counts"]
    assert counts["missing_frontmatter"]
    assert counts["missing_frontmatter"] == 9
    assert counts["dead_links"] == 18
    assert counts["duplicate_basenames"] == 1
    assert counts["empty_sections"] == 1
    assert counts["stale_index_entries"] == 3
    assert all(path.startswith("wiki/reading/") for path in prepared["lint_issue_paths"])
    assert prepared["lint_exit_code"] != 0


def test_rootless_research_restore_reads_real_products(tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    prepared = prepare_research_sources(tmp_path, monkeypatch)
    assert prepared["lint_counts"]["provenance_errors"] == 0
    assert prepared["lint_counts"]["orphans"] == 0
    assert len(prepared["revision_ids"]) >= 2
    vault = prepared["vault"]
    checkout = prepared["checkout"]
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)
    assert main(["backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout)]) == 0
    envelope = json.loads(capsys.readouterr().out)
    manifest = envelope["data"]
    assert envelope["ok"] is True
    assert manifest["schema"] == "video-paper-wiki.backup-manifest.v2"
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    manifest_path = outside / "manifest.json"
    manifest_path.write_bytes(canonicalize(manifest))
    manifest_path.chmod(0o600)
    archive = outside / "backup.zip"
    code, stdout = _operator(
        _admin(
            ROOT,
            "backup",
            "create",
            "--profile",
            "research-r1",
            "--vault-root",
            str(vault),
            "--checkout-root",
            str(checkout),
            "--manifest",
            str(manifest_path),
            "--destination",
            str(archive),
        ),
        b"backup create\n",
        ROOT,
    )
    assert code == 0, stdout
    created = json.loads(stdout)
    assert created["research_validation"] == "pending"
    archived = {row["path"]: row["sha256"] for row in manifest["files"]}
    combined = {**prepared["vault_files"], **prepared["checkout_files"]}
    for relative, digest in archived.items():
        assert combined[relative] == digest
        assert not relative.startswith((".git/", ".work/raw/", ".work/blobs/"))
        assert "/source-catalog/" not in relative
        assert "/reading-publication/" not in relative
        assert "/article-publication/" not in relative
    included = {(row["batch_id"], row["rule_id"]): row for row in manifest["coverage"]}
    for rule in ("code-evidence", "flow", "draft", "review", "plan"):
        assert included[("d1", rule)]["state"] == "included"
        assert included[("d1", rule)]["file_count"] > 0
    assert included[("b2", "draft")]["state"] == "included"
    assert included[("p1", "articles")]["state"] == "included"
    assert included[("ua", "articles")]["state"] == "included"
    assert included[("ua", "articles")]["file_count"] >= 2
    assert any(included[(batch, "domain")]["state"] == "included" for batch, _rule in included if _rule == "domain")
    assert any(row["state"] == "included" for (batch, rule), row in included.items() if rule == "experiments")
    for relative in (
        "wiki/meta/domain/heads.json",
        "wiki/meta/experiments/heads.json",
        "wiki/meta/articles/heads.json",
        "wiki/reading-notes/note.md",
        "wiki/meta/ledgers/source-ledger.json",
    ):
        assert relative in archived
    assert any(path.startswith("wiki/reading/") and path.endswith(".md") for path in archived)
    digest = manifest["manifest_sha256"]
    source_obs = _observe(vault)
    for relative, meta in _observe(checkout).items():
        if relative in source_obs and source_obs[relative] != meta:
            raise AssertionError(relative)
        source_obs[relative] = meta
    expected = {relative: meta for relative, meta in source_obs.items() if _whitelist(relative)}
    uninstalled = prepared["uninstalled"]
    vault_ids = {path.stem for path in vault.rglob("*") if path.is_file()}
    for record_id in (uninstalled["annotation_id"], uninstalled["review_id"], uninstalled["experiment_record_id"]):
        assert record_id not in vault_ids
        assert any(record_id in relative for relative in expected)
    original_vault = vault
    original_checkout = checkout
    original_bundle = prepared["bundle"]
    vault.rename(tmp_path / "gone-vault")
    checkout.rename(tmp_path / "gone-checkout")
    original_bundle.rename(tmp_path / "gone-bundle")
    assert not original_vault.exists()
    assert not original_checkout.exists()
    assert not original_bundle.exists()
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    code, stdout = _operator(
        _admin(
            ROOT,
            "backup",
            "restore",
            "--profile",
            "research-r1",
            "--archive",
            str(archive),
            "--manifest",
            str(manifest_path),
            "--expected-manifest-sha256",
            digest,
            "--restore-root",
            str(restore),
            "--upstream-root",
            str(UPSTREAM),
            "--config",
            str(POLICY),
        ),
        b"backup restore\n",
        ROOT,
    )
    restored_payload = json.loads(stdout)
    restored_obs = {relative: meta for relative, meta in _observe(restore).items() if _whitelist(relative)}
    assert restored_obs == expected
    assert {row["path"] for row in manifest["files"]} == {relative for relative, meta in expected.items() if meta["kind"] == "file"}
    assert {row["path"] for row in manifest["directories"]} == {relative for relative, meta in expected.items() if meta["kind"] == "dir"}
    for row in manifest["files"]:
        assert expected[row["path"]]["sha256"] == row["sha256"]
        assert expected[row["path"]]["mode"] == row["mode"]
    for row in manifest["directories"]:
        assert expected[row["path"]]["mode"] == row["mode"]
    assert (restore / ".work" / "p1" / "articles").is_dir()
    assert (restore / ".work" / uninstalled["domain_batch"] / "domain").is_dir()
    assert (restore / ".work" / uninstalled["review_batch"] / "domain" / "reviews").is_dir()
    assert (restore / ".work" / uninstalled["experiment_batch"] / "experiments" / "records").is_dir()
    assert audit_integrity(restore)["classification"] == "receipt_backed"
    assert not (restore / ".work" / "raw").exists()
    assert not (restore / ".work" / "blobs").exists()
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    _git(restore, "init", "-q", env=env)
    _git(restore, "fetch", "-q", str(ROOT), "HEAD", env=env)
    revision = _git(restore, "rev-parse", "FETCH_HEAD", env=env).strip()
    tracked = _git(restore, "ls-tree", "-r", "--name-only", revision, env=env)
    blocked = [
        line
        for line in tracked.splitlines()
        if line in {".raw", "wiki", ".work"} or line.startswith((".raw/", "wiki/", ".work/"))
    ]
    assert blocked == []
    _git(restore, "checkout", "-q", "--detach", revision, env=env)
    monkeypatch.chdir(restore)
    assert os.path.samefile(resolve_checkout_root(), restore)
    code_after = _cli_data(capsys, ["code-evidence", "status", "--batch-id", "d1"])
    assert code_after == prepared["code_status"]
    flow_after = build_flow_status(vault_root=str(restore), batch_id="d1")
    assert flow_after["selection"]["paper_ids"] == prepared["consumers"]["flow"]["selection"]["paper_ids"]
    assert flow_after["selection"]["question"] == prepared["question"]
    articles_after = status_article_store(vault_root=str(restore))
    staged_after = status_article_store(vault_root=str(restore), batch_id="ua")
    assert [row["article_id"] for row in articles_after["articles"]] == [
        row["article_id"] for row in prepared["consumers"]["articles"]["articles"]
    ]
    assert prepared["article_id"] in [row["article_id"] for row in staged_after["articles"]]
    history = article_history(vault_root=str(restore), article_id=prepared["article_id"], batch_id="ua")
    seen = [row["revision_id"] for row in history["revisions"]]
    assert prepared["revision_ids"][0] in seen
    assert prepared["revision_ids"][-1] in seen
    assert len(seen) >= 2
    domain_after = status_domain_store(vault_root=str(restore))
    experiment_after = status_experiment_store(vault_root=str(restore))
    assert domain_after == prepared["consumers"]["domain"]
    assert experiment_after == prepared["consumers"]["experiments"]
    flow_cli = _cli_data(capsys, ["flow", "status", "--vault-root", str(restore), "--batch-id", "d1"])
    assert flow_cli["selection"]["question"] == prepared["question"]
    domain_cli = _cli_data(capsys, ["domain", "status", "--vault-root", str(restore)])
    assert domain_cli == domain_after
    experiment_cli = _cli_data(capsys, ["experiments", "status", "--vault-root", str(restore)])
    assert experiment_cli == experiment_after
    articles_cli = _cli_data(capsys, ["articles", "status", "--vault-root", str(restore)])
    assert [row["article_id"] for row in articles_cli["articles"]] == [row["article_id"] for row in articles_after["articles"]]
    staged_cli = _cli_data(capsys, ["articles", "status", "--vault-root", str(restore), "--batch-id", "ua"])
    assert prepared["article_id"] in [row["article_id"] for row in staged_cli["articles"]]
    history_cli = _cli_data(
        capsys,
        ["articles", "history", "--vault-root", str(restore), "--article-id", prepared["article_id"], "--batch-id", "ua"],
    )
    history_ids = [row["revision_id"] for row in history_cli["revisions"]]
    assert prepared["revision_ids"][0] in history_ids
    assert prepared["revision_ids"][-1] in history_ids
    assert len(history_ids) >= 3
    reads = _research_reads(restore, manifest)
    flow_read = next(item["flow"] for item in reads["batches"] if item["batch_id"] == "d1")
    assert flow_read["selection"]["question"] == prepared["question"]
    retained = next(item["articles_read"] for item in reads["batches"] if item["batch_id"] == "p1")
    assert retained["mode"] == "retained_installed_staging"
    assert retained["retained_staging"]["records"]
    assert (restore / ".work" / "p1" / "articles").is_dir()
    merged = next(item["articles_read"] for item in reads["batches"] if item["batch_id"] == "ua")
    assert merged["mode"] == "merged"
    assert prepared["article_id"] in [row["article_id"] for row in merged["articles"]["articles"]]
    before_verify = _covered(restore, manifest)
    lint_after = lint_vault(vault_root=restore, upstream_root=UPSTREAM)
    catalog_code = None
    try:
        build_current_catalog(vault_root=restore, upstream_root=UPSTREAM, retrieval_config=POLICY)
    except ContractError as exc:
        catalog_code = exc.code
    verify_code = main(
        [
            "backup",
            "verify",
            "--profile",
            "research-r1",
            "--manifest",
            str(manifest_path),
            "--expected-manifest-sha256",
            digest,
            "--restore-root",
            str(restore),
            "--upstream-root",
            str(UPSTREAM),
            "--config",
            str(POLICY),
        ]
    )
    verify_payload = json.loads(capsys.readouterr().out)
    assert _covered(restore, manifest) == before_verify
    valid = bool(verify_payload.get("ok") and verify_payload.get("data", {}).get("valid") is True)
    log = tmp_path / "p3-r1-drill.json"
    log.write_text(
        json.dumps(
            {
                "manifest_sha256": digest,
                "archive_sha256": created["archive_sha256"],
                "source_anchor": manifest["source_anchor"],
                "vault_manifest_sha256": manifest["vault_manifest_sha256"],
                "receipt_sha256": prepared["receipt_sha256"],
                "batch_ids": manifest["scope"]["batch_ids"],
                "coverage": manifest["coverage"],
                "file_count": len(manifest["files"]),
                "code_state": code_after["state"],
                "revision_ids": prepared["revision_ids"],
                "candidate_revision": revision,
                "lint_exit_code": lint_after["exit_code"],
                "lint_counts": lint_after["data"]["summary"]["category_counts"],
                "catalog_code": catalog_code,
                "verify_code": verify_code,
                "verify_payload_ok": verify_payload.get("ok"),
                "operator_restore_code": code,
                "valid": valid,
                "original_roots_exist": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert log.parent == tmp_path
    assert log.name == "p3-r1-drill.json"
    assert code == 0, json.dumps(
        {
            "stdout": stdout.decode(),
            "lint_exit_code": lint_after["exit_code"],
            "lint_counts": lint_after["data"]["summary"]["category_counts"],
            "catalog_code": catalog_code,
            "verify_code": verify_code,
            "verify_ok": verify_payload.get("ok"),
            "verify_error": verify_payload.get("error"),
            "valid": valid,
        },
        ensure_ascii=False,
    )
    assert restored_payload["research_validation"] == "pending"
    assert restored_payload["verification"]["valid"] is False
    assert verify_code == 0, verify_payload
    assert verify_payload["ok"] is True
    assert verify_payload["data"]["valid"] is True


def _install_isolated(tmp_path: Path) -> Path:
    """Install the product and operator wheels into a fresh venv. Returns its Python."""

    import shutil
    import zipfile

    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir(parents=True)
    built = subprocess.run(
        ["uv", "build", "--wheel", "--offline", "--out-dir", str(wheel_dir)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    wheel = next(wheel_dir.glob("*.whl"))
    names = zipfile.ZipFile(wheel).namelist()
    assert any(name.endswith("schemas/video-paper-wiki.backup-manifest.v2.schema.json") for name in names)
    venv = tmp_path / "venv"
    created = subprocess.run(
        ["uv", "venv", str(venv), "--python", "3.12"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    python = venv / "bin" / "python"
    install_env = os.environ.copy()
    install_env["UV_LINK_MODE"] = "copy"
    installed = subprocess.run(
        ["uv", "pip", "install", "--offline", "--no-deps", "--python", str(python), str(wheel)],
        cwd=tmp_path,
        env=install_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stderr
    operator_dir = tmp_path / "operator-wheel"
    operator_dir.mkdir()
    operator_built = subprocess.run(
        ["uv", "build", "--wheel", "--offline", "--out-dir", str(operator_dir), str(ROOT / "operator")],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert operator_built.returncode == 0, operator_built.stderr
    operator_wheel = next(operator_dir.glob("*.whl"))
    operator_installed = subprocess.run(
        ["uv", "pip", "install", "--offline", "--no-deps", "--python", str(python), str(operator_wheel)],
        cwd=tmp_path,
        env=install_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert operator_installed.returncode == 0, operator_installed.stderr
    source_site = Path(subprocess.check_output([str(ROOT / ".venv" / "bin" / "python"), "-c", "import site; print(site.getsitepackages()[0])"], text=True).strip())
    target_site = next((venv / "lib").glob("python*/site-packages"))
    for child in source_site.iterdir():
        if child.name.startswith("video_paper_wiki"):
            continue
        destination = target_site / child.name
        if destination.exists():
            continue
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)
    return python


def test_installed_wheel_replays_research_restore(tmp_path: Path) -> None:
    """Install the built wheels and restore a v2 archive without importing the source tree."""

    python = _install_isolated(tmp_path)
    script = tmp_path / "replay.py"
    script.write_text(
        """
import hashlib, os, stat, sys
from pathlib import Path
from video_paper_wiki.backup_archive import create_backup_archive, restore_backup_archive
from video_paper_wiki.backup_manifest import build_research_backup_manifest
from video_paper_wiki.contracts import schema_by_title
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize

assert schema_by_title("video-paper-wiki.backup-manifest.v2")["properties"]["policy"]["const"] == "vpwiki-private-research-complete-set-r1"
assert "src/video_paper_wiki" not in Path(schema_by_title.__code__.co_filename).as_posix()
root = Path(sys.argv[1])
vault = root / "vault"
raw = b"wheel-pdf"
raw_sha = hashlib.sha256(raw).hexdigest()
raw_path = f".raw/captured/{raw_sha}.pdf"
page = b"wheel-page"
receipt = {"schema":"video-paper-wiki.operation-receipt.v1","sequence":1,"previous":None,"operation_id":"wheel","operation_type":"generic","intent_sha256":"0"*64,"writes":[{"path":"wiki/papers/wheel.md","mode":"create","before_sha256":None,"after_sha256":hashlib.sha256(page).hexdigest()}],"claimed_inputs":[{"path":raw_path,"mode":"read","sha256":raw_sha}]}
receipt["intent_sha256"] = receipt_intent_sha256(receipt)
receipt_raw = canonicalize(receipt)
files = {
    raw_path: raw,
    "wiki/papers/wheel.md": page,
    "wiki/meta/operations/000000000001-wheel.json": receipt_raw,
    "wiki/meta/registries/operation-head.json": canonicalize({"schema":"video-paper-wiki.operation-head.v1","sequence":1,"receipt_path":"wiki/meta/operations/000000000001-wheel.json","receipt_sha256":hashlib.sha256(receipt_raw).hexdigest()}),
}
for relative, data in files.items():
    target = vault / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
checkout = root / "checkout"
draft = checkout / ".work" / "b1" / "draft" / "paper-analysis-draft.v1.json"
draft.parent.mkdir(parents=True)
draft.write_bytes(b'{"draft":"wheel"}')
for tree in (vault, checkout):
    for path in tree.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    tree.chmod(0o700)
manifest = build_research_backup_manifest(vault, checkout)
import json, subprocess
vpwiki = Path(sys.executable).with_name("vpwiki")
listed = subprocess.run([str(vpwiki), "backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
assert listed.returncode == 0, listed.stderr
assert json.loads(listed.stdout)["data"]["manifest_sha256"] == manifest["manifest_sha256"]
manifest_path = root / "manifest.json"
manifest_path.write_bytes(canonicalize(manifest))
admin = Path(sys.executable).with_name("vpwiki-admin")
assert admin.is_file()
assert "operator/src" not in admin.read_text(encoding="utf-8", errors="ignore")
cli_archive = root / "cli-backup.zip"
import pty
master, slave = pty.openpty()
proc = subprocess.Popen([str(admin), "backup", "create", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout), "--manifest", str(manifest_path), "--destination", str(cli_archive)], stdin=slave, stdout=subprocess.PIPE, stderr=slave)
os.close(slave)
os.write(master, b"backup create\\n")
stdout, _stderr = proc.communicate(timeout=120)
os.close(master)
assert proc.returncode == 0, stdout
assert json.loads(stdout)["research_validation"] == "pending"
archive = root / "backup.zip"
create_backup_archive(vault_root=vault, checkout_root=checkout, manifest=manifest, destination=archive, profile="research-r1")
import shutil
vault.rename(root / "gone-vault")
checkout.rename(root / "gone-checkout")
shutil.rmtree(root / "gone-vault")
shutil.rmtree(root / "gone-checkout")
assert not (root / "gone-vault").exists()
assert not (root / "gone-checkout").exists()
restore = root / "restore"
restore.mkdir(mode=0o700)
restore_backup_archive(archive=archive, restore_root=restore, manifest=manifest, profile="research-r1", expected_manifest_sha256=manifest["manifest_sha256"])
for row in manifest["files"]:
    target = restore / row["path"]
    assert hashlib.sha256(target.read_bytes()).hexdigest() == row["sha256"]
    assert stat.S_IMODE(target.stat().st_mode) == row["mode"]
print("wheel-replay-ok")
""",
        encoding="utf-8",
    )
    replay = subprocess.run(
        [str(python), "-I", "-B", str(script), str(tmp_path / "data")],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert replay.returncode == 0, replay.stderr
    assert "wheel-replay-ok" in replay.stdout


def _installed_pty(argv: list[str], confirm: bytes, cwd: Path) -> tuple[int, bytes]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONSAFEPATH"] = "1"
    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=slave, stdout=subprocess.PIPE, stderr=slave)
    os.close(slave)
    os.write(master, confirm)
    try:
        stdout, _stderr = proc.communicate(timeout=240)
    finally:
        os.close(master)
    return proc.returncode or 0, stdout


def _installed_cli(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONSAFEPATH"] = "1"
    result = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    return result.returncode, result.stdout, result.stderr


def test_installed_cli_replays_the_full_research_drill(tmp_path: Path, monkeypatch) -> None:
    """Replay the rich drill through the installed product CLI and operator."""

    prepared = prepare_research_sources(tmp_path / "src", monkeypatch)
    python = _install_isolated(tmp_path / "install")
    vpwiki = python.with_name("vpwiki")
    admin = python.with_name("vpwiki-admin")
    assert vpwiki.is_file() and admin.is_file()
    vault = prepared["vault"]
    checkout = prepared["checkout"]
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    code, stdout, manifest_err = _installed_cli(
        [str(vpwiki), "backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout)],
        outside,
    )
    assert code == 0, stdout + manifest_err
    assert code == 0, stdout
    envelope = json.loads(stdout)
    manifest = envelope["data"]
    manifest_path = outside / "manifest.json"
    manifest_path.write_bytes(canonicalize(manifest))
    manifest_path.chmod(0o600)
    archive = outside / "backup.zip"
    create_code, create_stdout = _installed_pty(
        [
            str(admin),
            "backup",
            "create",
            "--profile",
            "research-r1",
            "--vault-root",
            str(vault),
            "--checkout-root",
            str(checkout),
            "--manifest",
            str(manifest_path),
            "--destination",
            str(archive),
        ],
        b"backup create\n",
        outside,
    )
    assert create_code == 0, create_stdout
    created = json.loads(create_stdout)
    digest = manifest["manifest_sha256"]
    vault.rename(tmp_path / "gone-vault")
    checkout.rename(tmp_path / "gone-checkout")
    prepared["bundle"].rename(tmp_path / "gone-bundle")
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    restore_code, restore_stdout = _installed_pty(
        [
            str(admin),
            "backup",
            "restore",
            "--profile",
            "research-r1",
            "--archive",
            str(archive),
            "--manifest",
            str(manifest_path),
            "--expected-manifest-sha256",
            digest,
            "--restore-root",
            str(restore),
            "--upstream-root",
            str(UPSTREAM),
            "--config",
            str(POLICY),
        ],
        b"backup restore\n",
        outside,
    )
    restored_payload = json.loads(restore_stdout)
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    _git(restore, "init", "-q", env=env)
    _git(restore, "fetch", "-q", str(ROOT), "HEAD", env=env)
    revision = _git(restore, "rev-parse", "FETCH_HEAD", env=env).strip()
    tracked = _git(restore, "ls-tree", "-r", "--name-only", revision, env=env)
    blocked = [line for line in tracked.splitlines() if line in {".raw", "wiki", ".work"} or line.startswith((".raw/", "wiki/", ".work/"))]
    assert blocked == []
    _git(restore, "checkout", "-q", "--detach", revision, env=env)
    consumers: dict[str, object] = {}
    for name, args in (
        ("code", ["code-evidence", "status", "--batch-id", "d1"]),
        ("flow", ["flow", "status", "--vault-root", str(restore), "--batch-id", "d1"]),
        ("domain", ["domain", "status", "--vault-root", str(restore)]),
        ("experiments", ["experiments", "status", "--vault-root", str(restore)]),
        ("articles", ["articles", "status", "--vault-root", str(restore)]),
    ):
        status, body, err = _installed_cli([str(vpwiki), *args], restore)
        consumers[name] = {"code": status, "ok": status == 0}
        if status == 0:
            payload = json.loads(body)
            assert payload["ok"] is True
            if name == "code":
                assert payload["data"] == prepared["code_status"]
            if name == "flow":
                assert payload["data"]["selection"]["question"] == prepared["question"]
        else:
            consumers[name]["stdout"] = body[-800:]
            consumers[name]["stderr"] = err[-800:]
    before_verify = _covered(restore, manifest)
    verify_code, verify_stdout, _verify_err = _installed_cli(
        [
            str(vpwiki),
            "backup",
            "verify",
            "--profile",
            "research-r1",
            "--manifest",
            str(manifest_path),
            "--expected-manifest-sha256",
            digest,
            "--restore-root",
            str(restore),
            "--upstream-root",
            str(UPSTREAM),
            "--config",
            str(POLICY),
        ],
        outside,
    )
    verify_payload = json.loads(verify_stdout) if verify_stdout else {}
    assert _covered(restore, manifest) == before_verify
    valid = bool(verify_payload.get("ok") and verify_payload.get("data", {}).get("valid") is True)
    log = tmp_path / "installed-drill.json"
    log.write_text(
        json.dumps(
            {
                "create_code": create_code,
                "restore_code": restore_code,
                "restore_error": restored_payload.get("error"),
                "verify_code": verify_code,
                "verify_error": verify_payload.get("error"),
                "consumers": consumers,
                "candidate_revision": revision,
                "valid": valid,
                "manifest_sha256": digest,
                "archive_sha256": created.get("archive_sha256"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert restore_code == 0, log.read_text(encoding="utf-8")
    assert restored_payload["research_validation"] == "pending"
    assert restored_payload["verification"]["valid"] is False
    assert verify_code == 0, verify_payload
    assert verify_payload["ok"] is True
    assert verify_payload["data"]["valid"] is True
