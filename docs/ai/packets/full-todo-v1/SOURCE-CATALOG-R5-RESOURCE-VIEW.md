# SOURCE-CATALOG R5 — use the captured generation resources

R1/R2/R3 describe complete retained generation resources. Inspection of the
actual implementation found two integration requirements: contracts._registry
is cached across the process, and the legacy/current compilers read taxonomy
through read_projection_resource_bytes. Merely hashing current resource files
would not bind a previously cached validator to those captured bytes.

This amendment adds exactly resources.py and contracts.py to the owned paths
(19 total, allowed-paths-r2.json). Their existing default behavior remains.
All catalog interfaces, row shapes, limits, profile bytes and R4 delivery gate
remain unchanged. There is no global monkeypatch or validator-cache clearing.

## Per-call retained resource view

resources.py provides a private context manager backed by ContextVar. A view
contains an immutable copy of exact captured resource bytes, keyed by resource
kind and fixed filename, and the complete captured schema filename set. Only
the catalog's already retained generation session enters this context. The
context spans audit, source collection/compilation, catalog validation and result
assembly, and resets its token on every exit. It does not install resources,
change CWD, rewrite module files or alter the caller's byte mapping.

Inside the context, schema_resource_names, schema loading and projection-resource
reads use that captured view. A missing requested resource remains missing;
there is no packaged, repository or CWD fallback. This applies to compiler
taxonomy and all transitive schema references as well as the new catalog schema.
The source/package origin selection and complete sets are still independently
retained and verified by the IO session described by R2.

contracts._registry selects a registry built from the active view when present.
That registry may be cached only in that particular context's private state.
Outside a view it uses the existing ordinary cached registry. All direct
registry users, schema_by_title and validator construction must follow that
same selector. A previously primed default registry cannot supply a schema to
the catalog view. Two independent contexts cannot share a cached registry; nested
contexts restore the outer registry and exceptional exits restore the default.
Schema parsed objects are private to their registry; no context mutates another
context or the default registry's schemas. Existing default callers and resource
lookup behavior remain compatible.

The generation digest still uses exact original resource bytes, including their
whitespace. Registry construction does not canonicalize or reserialize those
bytes into new provenance. Original parser/evidence JSON handling remains
separate; this view does not reinterpret historical bbox floats or ledger wire.
The implementation manifest identifies the installed Python source files;
arbitrary hot reloading/monkeypatching of process code is outside the catalog
runtime contract and requires a new process for a changed installation.

## Required implementation checks

- Prime the default schema registry, then enter a view with a deliberate safe
  schema difference: only the view's validator observes it, and its transitive
  references come from the same view. After exit, the default registry is intact.
- Exercise two nested views and isolated execution contexts, including ordinary
  validation exceptions. No resource or registry state leaks between them.
- After generation capture, prohibit underlying packaged/repository/CWD resource
  reads during the actual source collector/compiler. The catalog succeeds using
  captured resources only; missing captured resources refuse without fallback.
- Change a schema/taxonomy/profile named file or resource set during projection:
  final retained verification still returns WORK_PATH_UNSAFE even when validation
  also fails. The private view cannot hide a changed original resource.
- Re-run ordinary legacy compiler/schema/resource tests, both full suites and
  actual installed-wheel resource parity. R5 supplies no authority to change
  schema/profile semantics, suppress validation, write a Vault or close a gate.
