"""CLI adapter for articles check, export, history, import, render, and status."""

from __future__ import annotations

import sys

from video_paper_wiki.article_context import (
    EXPORT_COMMAND,
    ArticleContextError,
    export_article_context,
)
from video_paper_wiki.article_revision import (
    ArticleRevisionError,
    article_history,
    check_article_revision,
    import_article_revision,
    render_article_revision,
    status_article_store,
)
from video_paper_wiki.article_store import ArticleStoreError
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_publication import DomainPublicationError
from video_paper_wiki.domain_relations import DomainRelationError
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.domain_versions import DomainVersionsError
from video_paper_wiki.envelope import emit_error, emit_staging_error
from video_paper_wiki.experiment_comparability import ExperimentComparabilityError
from video_paper_wiki.experiment_matrix import ExperimentMatrixError
from video_paper_wiki.experiment_publication import ExperimentPublicationError
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.graph_projection import GraphProjectionError
from video_paper_wiki.graph_query import GraphQueryError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError

CHECK_COMMAND = "articles.check"
HISTORY_COMMAND = "articles.history"
IMPORT_COMMAND = "articles.import"
RENDER_COMMAND = "articles.render"
STATUS_COMMAND = "articles.status"


def _emit_success(command, data):
    envelope = {"ok": True, "command": command, "data": data}
    sys.stdout.buffer.write(canonicalize(envelope) + b"\n")
    sys.stdout.buffer.flush()
    return 0


def _emit_coded_error(command, exc):
    return emit_error(
        command,
        exc.code,
        exc.message,
        exc.details,
        exit_code=exc.exit_code,
    )


def _run(command, function):
    try:
        return _emit_success(command, function())
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
    except DomainPublicationError as exc:
        return _emit_coded_error(command, exc)
    except DomainStoreError as exc:
        return _emit_coded_error(command, exc)
    except DomainProposalError as exc:
        return _emit_coded_error(command, exc)
    except StagingError as exc:
        return emit_staging_error(command, exc)
    except ContractError as exc:
        return emit_error(
            command,
            exc.code,
            exc.message,
            {
                "instance_pointer": exc.details.get("instance_pointer", ""),
                "next_action": "repair_input",
                **exc.details,
            },
            exit_code=getattr(exc, "exit_code", 2),
        )
    except SecureIOError as exc:
        return emit_error(
            command,
            exc.code,
            exc.message,
            {"instance_pointer": "/input", "next_action": "repair_input", **exc.details},
            exit_code=getattr(exc, "exit_code", 2),
        )


def run_articles_export_command(args):
    return _run(
        EXPORT_COMMAND,
        lambda: export_article_context(
            vault_root=args.vault_root,
            question=getattr(args, "question", None),
            paper_ids=getattr(args, "paper_ids", None),
            article_id=getattr(args, "article_id", None),
            revision_id=getattr(args, "revision_id", None),
            batch_id=getattr(args, "batch_id", None),
            section_id=getattr(args, "section_id", None),
            instructions=getattr(args, "instructions", "") or "",
        ),
    )


def run_articles_import_command(args):
    return _run(
        IMPORT_COMMAND,
        lambda: import_article_revision(
            vault_root=args.vault_root,
            batch_id=args.batch_id,
            context=args.context,
            document=args.document,
            recorded_by=args.recorded_by,
            recorded_at=args.recorded_at,
            previous_revision_id=getattr(args, "previous_revision_id", None),
            target_section_id=getattr(args, "target_section_id", None),
            instructions=getattr(args, "instructions", "") or "",
        ),
    )


def run_articles_check_command(args):
    return _run(
        CHECK_COMMAND,
        lambda: check_article_revision(
            vault_root=args.vault_root,
            article_id=args.article_id,
            revision_id=args.revision_id,
            batch_id=getattr(args, "batch_id", None),
        ),
    )


def run_articles_render_command(args):
    return _run(
        RENDER_COMMAND,
        lambda: render_article_revision(
            vault_root=args.vault_root,
            batch_id=args.batch_id,
            article_id=args.article_id,
            revision_id=args.revision_id,
        ),
    )


def run_articles_status_command(args):
    return _run(
        STATUS_COMMAND,
        lambda: status_article_store(
            vault_root=args.vault_root,
            batch_id=getattr(args, "batch_id", None),
        ),
    )


def run_articles_history_command(args):
    return _run(
        HISTORY_COMMAND,
        lambda: article_history(
            vault_root=args.vault_root,
            article_id=args.article_id,
            batch_id=getattr(args, "batch_id", None),
        ),
    )
