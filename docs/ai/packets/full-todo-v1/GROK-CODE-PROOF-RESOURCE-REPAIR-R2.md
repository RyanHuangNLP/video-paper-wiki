# Repair the existing CODE resource candidate — R2

You are the sole implementation author, Grok Build grok-4.6 / xhigh.
Read `invocation-inputs.json` and all its named prepared input copies in this
directory. This call allows only `read_file` on those exact files. No repository
access, unrelated files, credentials, session history, shell, edits, writes,
execution, web/network tools, MCP, subagents or test runs. Normal permission
mode stays enabled. You produce a declarative repair response only.

Your previous complete generator and resource-test output are preserved as
`generate_code_proof_resources.py` and `test_code_proof_resources.py`. Repair
only the confirmed boundary defects and test deficiencies described in
`CODE-PROOF-RESOURCE-REPAIR-R2.md`. Preserve every unrelated definition and test.
The R2 packet changes the response mechanism to exact literal replacements
because complete base files now exist. It also explicitly resolves the input
bundle-directory grammar; it does not change output batch/stored paths.

R12 remains the resource contract and R9 remains the repository grammar. These
copies provide context, not authorization to redesign other schema branches or
implement public commands. The original fourteen product paths and two-file
authorship remain unchanged. Accepted CONFIG source stays at local head
4ab1830939cd41981983909763434d5612df6070, tree
22fc77a38704386eaad5ad9be8a9268f0a1a5392, without changes.

`repair-boundary-facts-r2.json` contains actual independent schema probe results
and compact accepted-kernel boundary facts. `repair-positive-seeds-r2.json`
contains exact selected values from the complete 264-case preparation fixture.
These use the preparation zero profile hash; they are synthetic evidence, not
public command executions. Do not hardcode sample order, sample names, digests
or profile hash. The final fixture is separately rebuilt against the corrected
actual profile. All 264 original preparation shapes already validate under R1;
the omitted boundaries and discriminating negatives are what need repair.

Review each bug and its test consequences, then return exactly one block:

BEGIN_PATCH code-resource-r2
```json
{
  "schema": "full-todo.code-resource-exact-text-patch.v1",
  "base_files": {
    "generate_code_proof_resources.py": "df798bf22b08d385c1b2de712d950e7978f5d89836486beb703d8bb1d8e749b2",
    "test_code_proof_resources.py": "19c8d6355bfe8db22c37ec7abce96409bf9d8cef989443ef560ece1af1def74f"
  },
  "edits": [],
  "brief": {
    "changes": [],
    "tests_run": false,
    "unresolved_questions": []
  }
}
```
END_PATCH code-resource-r2

The empty arrays above describe the JSON shape. Supply nonempty `edits` and
`changes` containing your complete actual repairs. Each closed edit object has
only `file`, `old`, and `new`. `old` is nonempty and must match exactly once in
that file after preceding edits; `new` is the complete literal replacement.
Use at most 64 edits. Correct JSON escaping must preserve real newlines and
literal regex backslashes. Do not output a full file, executable patch script,
shell command, placeholder or manual resource-byte replacement. Do not modify
the existing schema-count test or fixture bundle.

The test repairs must be diagnostic: validate each positive before mutation,
exercise distinct closed branch shapes, preserve typed dict/list path keys,
change one field per negative, and target actual declaration/Git fields.
Cover repository exclusions before URL suffixes as well as standalone forms;
preserve legitimate leading punctuation and input case. For input directories,
preserve `.work/` scope and alias/control exclusions without the output batch
identifier restriction. Do not infer semantic identity, filesystem safety or
byte-limit proof from schema validity. An explicitly constructed unsafe Git
target can be a schema-only positive if it validates before negative mutation.

The generator remains a self-contained offline stdlib-only constructor which
creates only ten schemas and one profile below a supplied absent directory.
All source/package reads, profile hashing order, resource inventory, exact
serialization and side-effect restrictions remain as already implemented and
specified in R12/R2. Do not execute it. The coordinator will freeze the patched
files, review them independently, generate fresh resources, replay boundaries,
rebuild fixtures and run local tests/wheel checks after source integration.
Report any real unresolved contradiction in the brief, and do not claim tests,
resource acceptance, delivery or CODE completion.
