"""CLI adapter for python -m video_paper_wiki.reading build."""

from __future__ import annotations

import sys

from video_paper_wiki.article_context import ArticleContextError
from video_paper_wiki.article_revision import ArticleRevisionError
from video_paper_wiki.article_store import ArticleStoreError
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.domain_claims import DomainClaimsError
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_publication import DomainPublicationError
from video_paper_wiki.domain_relations import DomainRelationError
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.domain_structure import DomainStructureError
from video_paper_wiki.domain_versions import DomainVersionsError
from video_paper_wiki.envelope import emit_error, emit_staging_error
from video_paper_wiki.experiment_comparability import ExperimentComparabilityError
from video_paper_wiki.experiment_matrix import ExperimentMatrixError
from video_paper_wiki.experiment_publication import ExperimentPublicationError
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.graph_projection import GraphProjectionError
from video_paper_wiki.graph_query import GraphQueryError
from video_paper_wiki.identity import IdentityError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.reading.view import ReadingViewError, build_reading_views
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError

BUILD_COMMAND = "reading.build"


def _emit_success(command, data):
    envelope = {"ok": True, "command": command, "data": data}
    sys.stdout.buffer.write(canonicalize(envelope) + b"\n")
    sys.stdout.buffer.flush()
    return 0


def _exit_code(exc):
    code = getattr(exc, "code", "")
    if code == "READING_BASIS_CHANGED" or str(code).endswith("_CHANGED") or str(code).endswith("_STALE"):
        return 75
    return getattr(exc, "exit_code", 2)


def _details(exc, fallback_pointer="/input", fallback_action="repair_input"):
    details = dict(getattr(exc, "details", None) or {})
    if "instance_pointer" not in details:
        details["instance_pointer"] = fallback_pointer
    if "next_action" not in details:
        details["next_action"] = fallback_action
    return details


def _emit_coded_error(command, exc):
    return emit_error(
        command,
        exc.code,
        exc.message,
        _details(exc),
        exit_code=_exit_code(exc),
    )


def _run(command, function):
    try:
        return _emit_success(command, function())
    except ReadingViewError as exc:
        return _emit_coded_error(command, exc)
    except ArticleStoreError as exc:
        return _emit_coded_error(command, exc)
    except ArticleContextError as exc:
        return _emit_coded_error(command, exc)
    except ArticleRevisionError as exc:
        return _emit_coded_error(command, exc)
    except GraphProjectionError as exc:
        return _emit_coded_error(command, exc)
    except GraphQueryError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentMatrixError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentComparabilityError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentPublicationError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentStoreError as exc:
        return _emit_coded_error(command, exc)
    except DomainRelationError as exc:
        return _emit_coded_error(command, exc)
    except DomainVersionsError as exc:
        return _emit_coded_error(command, exc)
    except DomainStructureError as exc:
        return _emit_coded_error(command, exc)
    except DomainClaimsError as exc:
        return _emit_coded_error(command, exc)
    except DomainPublicationError as exc:
        return _emit_coded_error(command, exc)
    except DomainStoreError as exc:
        return _emit_coded_error(command, exc)
    except DomainProposalError as exc:
        return _emit_coded_error(command, exc)
    except IdentityError as exc:
        return _emit_coded_error(command, exc)
    except StagingError as exc:
        return emit_staging_error(command, exc)
    except ContractError as exc:
        return emit_error(
            command,
            exc.code,
            exc.message,
            _details(exc),
            exit_code=getattr(exc, "exit_code", 2),
        )
    except SecureIOError as exc:
        return emit_error(
            command,
            exc.code,
            exc.message,
            _details(exc),
            exit_code=getattr(exc, "exit_code", 2),
        )


def run_reading_build_command(args):
    return _run(
        BUILD_COMMAND,
        lambda: build_reading_views(
            vault_root=args.vault_root,
            batch_id=args.batch_id,
            paper_id=getattr(args, "paper_id", None),
            articles_batch=getattr(args, "articles_batch", None),
        ),
    )
