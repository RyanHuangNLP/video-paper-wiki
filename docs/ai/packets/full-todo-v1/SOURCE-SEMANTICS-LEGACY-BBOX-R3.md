# SOURCE-SEMANTICS compatibility amendment, revision 3

R2 remains immutable. This amendment resolves one conflict found by executing
the existing accepted v1 PDF fixture: its optional display `bbox` contains finite
floating-point coordinates. R2 simultaneously required unchanged legacy evidence
behavior and a blanket no-float preflight. The legacy guarantee takes precedence
at the explicit v1 evidence branches only.

Source association, display, Markdown locator, event and record metadata remain
integer-only JSON. The new evidence wrappers, assessment histories and prospective
compiler may accept exact finite Python floats only in an admitted legacy PDF
evidence object's optional four-element `bbox` array. The existing v1 validator,
exact rational wire representation, fingerprint identity fields and errors remain
unchanged. No float is admitted into new content-derived identity material; legacy
PDF bbox is optional display metadata excluded by the frozen legacy fingerprint.
Nonfinite values, floats elsewhere and malformed bbox fields still refuse.

Implementation must locate this exception only in actual evidence positions:
the evidence-wrapper item itself, each assessment claim's evidence array, and each
compiler paper group's claims' evidence arrays. A coincidental `kind: pdf` object
elsewhere does not bypass preflight. The compiler's unchanged v1 code alignment
also admits PDF locators in `code[].alignment.officiality.evidence[]`; those exact
declared locator slots receive the same optional bbox treatment. These full objects are still checked for
cycles, exact built-in types, integer/depth/node/string limits and stable traversal
before schema validation. The seven allowed schemas and 29 allowed paths do not
change. Existing v1 production code and schemas stay byte-identical.

Acceptance adds complete legacy PDF float-bbox round trips, exact old fingerprint
equality, mixed PDF/Markdown fingerprint independence from bbox display changes,
legacy and mixed compile compatibility, and fake-PDF objects in unrelated fields
rejected by integer-only preflight. Existing raw locator span coordinates stay
exact integers and are never estimated PDF boxes.

Source is a development draft. Both independent reviewers must confirm this
bounded technical resolution before the final R3 contract freeze and candidate.
