# Resource implementation interface facts — R1

This is a bounded local interface capsule for the resource-generation packet.
It supplies existing package facts referenced by R4/R7/R12; it does not amend
kernel results or implement public command behavior. The final freeze binds the
source files from which these facts were checked.

## Accepted local source

The accepted CONFIG head is
`4ab1830939cd41981983909763434d5612df6070`, with tree
`22fc77a38704386eaad5ad9be8a9268f0a1a5392`. Its parent
`b46e106e48438f18cbbcf0c3fbee8f0a7524f071` is the accepted Git-kernel head.
These are local kernel acceptances. Public CODE commands and the new resources
have not yet been implemented or accepted.

Existing imports available to the product resource tests are:

```python
from video_paper_wiki.code_git_objects import CODE_GIT_PROFILE_LIMITS
from video_paper_wiki.code_config_parser import CODE_CONFIG_PROFILE_LIMITS
```

These are the complete five-key and thirteen-key hard-limit maps specified by
the contracts. The resource generator must not import them or any project code;
its resource definitions remain self-contained. The tests may compare their
values with the literal R12 maxima and the generated profile.

## Existing batch and package conventions

The existing `staging.py` batch validator uses full-match semantics with maximum
length 128 and this expression:

```text
^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?$
```

A batch is therefore one ASCII alphanumeric character, or 2–128 characters
beginning and ending in ASCII alphanumerics with only alphanumerics, underscore
and hyphen inside. Dot and whitespace are not permitted. The new public API
requires exact strings as specified by R7. JSON Schema search-pattern semantics
must preserve the existing full-match language, including rejection of terminal
line separators; an unqualified final `$` alone does not guarantee that.

Requested Git paths remain a different grammar: 1–32 slash-separated portable
ASCII components, at most 512 bytes, each from `[A-Za-z0-9._-]+`, excluding `.`,
`..` and case-insensitive `.git`. Roles are the six R2 values `readme`,
`citation`, `license`, `implementation`, `configuration`, and `entrypoint`.
Keep logical Git paths distinct from checkout-relative stored body/output paths
and from a batch ID.

The imported source package is `src/video_paper_wiki`. Its profile directory is
`src/video_paper_wiki/profiles`; source schemas are the same checkout's `schemas`
directory. The current wheel packages `src/video_paper_wiki` and
`src/video_paper_wiki_research`, and force-includes the checkout `schemas`
directory as `video_paper_wiki/schemas`. The generated profile belongs inside
the imported package's `profiles` directory. No package metadata edit is in scope.

The existing `tests/contract/test_schemas.py` assertion is exactly
`assert len(schema_paths) == 71`. The coordinator changes only that number to 81
after all ten new schemas are generated and reviewed. Grok returns only the new
resource test module, not a replacement for this existing file.

## Installed validation interfaces

The checked local dependency versions are `jsonschema 4.26.0`,
`referencing 0.37.0` and `pytest 9.1.1`. Public interfaces inspected locally:

```text
Registry(retrieve=...)
Registry.with_resources(pairs)
Resource.from_contents(contents, default_specification=...)
NoSuchResource(ref)
validators.extend(validator, validators=(), version=None,
                  type_checker=None, format_checker=None)
Draft202012Validator(schema, resolver=None, format_checker=None,
                    *, registry=..., _resolver=None)
```

Use `Registry`, `Resource` from `referencing`, `NoSuchResource` from
`referencing.exceptions`, and `Draft202012Validator`, `validators` from
`jsonschema`. Use the documented type-checker extension to enforce exact ints.
Do not depend on private internals, a nonexistent exported error-code constant,
or a registry that discovers arbitrary neighboring resources.

The final positive test bundle uses the exact closed transport from the output
contract. Test code should validate every case and select mutation seeds by
their declared title/kind/state/format, without depending on incidental file
ordering or on an unavailable public CODE function. The common profile case is
validated separately. Synthetic sample assertions do not authenticate a provider
or prove that a repository is official.
