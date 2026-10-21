# SOURCE-CONVERSION R2 — timestamp transport precision

This precise amendment is read with R1 SHA-256
464e3e98e8aa51199df5b93834bf196e49829918e95589c29de0c7572dfb5c72.
All input/source/history and allowed-path decisions in R1 remain unchanged.

`proposed_at` must be an explicit calendar-valid whole-second UTC timestamp,
exactly YYYY-MM-DDTHH:MM:SSZ. Both existing source and claim ledgers require
that 20-character precision; conversion must not accept a fractional value and
later truncate it or fail unpredictably during publication assembly. This does
not narrow metadata.published_at, whose existing date/UTC timestamp union still
accepts its supported fractional precision.

Only changed objects persist proposed_at. A changed claim/source ledger sets
its generated_at to proposed_at and refuses a value before its existing
calendar-valid generated_at. A changed paper record likewise checks updated_at;
a new/invalidation event checks its predecessor. Equal timestamps are allowed.
An unchanged no-op validates the proposed_at grammar but does not compare it to
persisted dates or manufacture any timestamp update. Preserve the existing
source-ledger snapshot before its first metadata/page-link modification using
the ordinary source-publication helper.
