# Workflow and result interpretation

1. Run `formal-source plan --workspace-root PATH --paper-id LIGHT_ID --batch-id ID`.
   The workspace must be an existing `.work` directory in the current checkout.
2. Supply the external `markdown-capture-approval-ref.v1` via
   `formal-source prepare --plan PATH --approval-ref PATH`. Missing approval leaves only the plan.
3. Run `formal-source inspect --prepared PATH --operation-id ID --upstream-root PATH --vault-root PATH`.
   `awaiting_operator_capture` means create; `capture_reused` carries no child transaction authorities.
4. After an independently authorized operator performs create, bind its actual result with
   `formal-source bind-result --authority PATH --result PATH --before PATH --after PATH`.
5. Run `formal-source admit --authority PATH --capture-result PATH --batch-id NEW_ID
   --operation-id NEW_ID --vault-root PATH --upstream-root PATH --ingested-at UTC`.
   Existing audited registrations can omit the separate capture result.

Save the underlying data objects from the single JSON envelopes: `inspect` nests the capture object
under `data.authority`, while `bind-result` returns its authority directly under `data`.
Before/after descriptors are path-keyed objects, with `null` for an absent file or `{sha256, mode}`
for a regular file; modes are integer permission bits. They are external observations, never desired values.

`source_registration_prepared` remains unpublished until operator execution. Capture does not create
a canonical receipt. Admission creates an inspectable ingest publication that claims the captured
Markdown path. `source_already_registered` requires both the exact ledger source and a valid audited
raw claim. An unproven matching raw file is an orphan and must not be admitted without capture evidence.

Repeated identical operations reuse staged bytes. Conflicting bytes, stale metadata, legacy
PDF/code authority objects, unsafe paths and replaced file identities fail closed. Fix the stated
input or prepare a new batch; do not overwrite competing staged files. Preserve original PDFs locally.

See `docs/formal-source-quickstart.md` for complete commands and the separate operator boundaries.
