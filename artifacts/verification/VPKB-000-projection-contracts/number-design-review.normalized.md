# Independent projection numeric review (proposal, not frozen)

Reviewed repository HEAD 5f4c186566c15ab5ee8df10c587e4709d6223f32 and pinned
upstream 9f8c1199047eac2c3828496279fbb7ba9540b90b. No implementation changed.
Reproducer: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python
<TEMP_ROOT>/vpkb-projection-steward-number-review.py (repository cwd), exit 0.
The adjacent JSON preserves exact candidate bytes and SHA256 vectors.

## PDF identity finding

No bbox/identity conflict exists. identity.py:60-69 fixes PDF identity fields
without bbox/charspan; :520-565 projects those fields before JCS. Contract test
identity.py:56-67 and identity/formulas.json explicitly freeze the exclusions.
A valid paper-analysis-draft with bbox [10.25,20.5,100.125,40.75] passes public
validate_document. Fractional bbox evidence retains the frozen fingerprint
00eb9c8b0e102b30fb95278afc606b456f00c051af5981f3740af2a0f5fbf73b.
Direct JCS of the whole draft refuses CANONICAL_JSON_INVALID, as its integer-only
scope requires; this is not the identity path. Preserve all existing goldens/JCS.

## Recommended exact comparison domain

Use a separate versioned runtime comparison codec, after complete emitter-shape
validation and removal of ONLY the profile's exact root volatile field:
chunk /created_at; BM25 /updated_at. Keep required timestamp validation before
removal. Do not remove similarly named nested keys. Keep complete object content,
array order, integer semantics, hashes, params k1/b and avg_dl material.

Candidate grammar (Architect chooses final names/version):
null -> ["null"]
bool -> ["bool", value]
string -> ["string", value]
number -> ["number", numerator, denominator]
array -> ["array", [encoded elements in original order]]
object -> ["object", [[key, encoded value], ... in UTF-16BE key order]]

Integers use n/1. Finite binary64 floats use their exact reduced as_integer_ratio.
All zeros use 0/1; 1 and 1.0 compare equal ONLY where the profile allows a numeric
field. Strict integer fields must reject 1.0 before comparison. true differs from
1. No tolerance, rounding, stringification, or reordering of arrays. Reject
NaN/infinity, non-string object keys, lone surrogates, cycles/non-JSON values;
apply explicitly frozen traversal/resource limits with typed errors. This
review prototype does not implement production cycle/depth/size defenses.

The optional fingerprint wrapper used for review is
{"codec":"vpwiki.runtime-tree.v1","profile":"<profile-id>","tree":<tree>}.
Serialize with the existing integer-only JCS and hash SHA256. The codec/profile
IDs separate this from identity or receipt canonical JSON. The representation
is comparison material, never an upstream emitted JSON replacement. All node
types are tagged, so input arrays/objects imitating a number tag cannot collide.

This is preferable to an ad hoc stdlib JSON serializer here: JSON sort_keys uses
Unicode code-point ordering rather than UTF16; ordinary dumps distinguishes 1
from 1.0 and -0.0 from 0; selecting float/exponent spellings otherwise needs an
additional numeric serialization spec. The tagged ratio format states exactly
which semantic equalities are intended, without changing the frozen JCS.
Extra material size is a reasonable tradeoff for a bounded derived comparison
fingerprint, not a reason to rewrite upstream artifacts.

Parsing remains an explicit boundary: the ratio is the exact parsed binary64
value, not the rational value of a decimal JSON token. If an API accepts raw
JSON bytes it must specify duplicate-key rejection, nonfinite/overflow handling,
and its float parsing policy; it cannot claim byte/decimal-token exactness after
ordinary JSON parsing. Decimal/Fraction/custom numeric types should not silently
enter this codec. Canonical byte identity remains separate from runtime equality.

## Source evidence and vectors

Pinned bm25-index.py:118-119 fixes k1=1.5,b=.75; :532 uses Python division for
avg_dl; :537-544 emits the complete index. :664's math.isclose verifies an
internal length relationship, but MUST NOT become the runtime comparator.
The previously accepted portable fixture index contains params 1.5/.75,
avg_dl=36.2, doc_count=5. Re-encoding its timestamp-stripped full value succeeds;
changing b by one ULP changes comparison bytes. No upstream private API ran.

The adjacent JSON includes canonical UTF8 and hashes for null, bool, 1/1.0,
0/-0, 0.1 exact ratio 3602879701896397/36028797018963968, nextafter(1,+inf),
1.5=3/2, .75=3/4, minimum subnormal, largest finite binary64, tag-like input array,
and U+10000 versus U+E000 UTF16 key ordering. Independent stdlib serialization of
the already encoded wrapper agrees with the project JCS for every vector.

Required future acceptance additionally covers shape validation before volatile
removal, exact changed k1/b/avg_dl behavior, nested timestamp materiality, duplicate
keys/raw decoding policy, invalid scalar and collection refusal, resource limits,
and strict integer counts rejecting 1.0. No production release or 001 acceptance
is implied by this prototype.
