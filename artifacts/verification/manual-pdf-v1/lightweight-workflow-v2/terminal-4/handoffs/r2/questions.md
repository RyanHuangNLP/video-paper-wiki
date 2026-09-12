# T4 r2 findings

## T3 publication-order window (reproduced, do not patch here)

Imported T3 r3 `light_workflow.py` SHA-256 `73bc3982273189f739481473d786fea8499c626be9bf380c9b9178326cd729d0`.

Replay of Architect `publication_edge_probe.py` against T4 source (synthetic only; results in `logs/r2-publication-edge.json`):

- control: `ok=true`, `state=awaiting_model`, 1 session
- last_staged_file_move: injected source edit during final staged `Path.replace`; result `ok=true`, `status=OK`, `state=stale`, 1 new session
- before_publish_hook: injected source edit at `HOOK_BEFORE_SESSION_PUBLISH`; same `ok=true/OK/stale` and a new session

Architect already recorded `CHANGES_REQUIRED_T3_R3_PUBLICATION_ORDER` and withheld T4 full-suite gate. T4 will not edit `light_workflow.py`. Need either Architect `lane3-r3-acceptance.json` that explicitly accepts this r3, or a new official T3 revision that closes the window.

## Official T4 final gate

`architect-overall-r2/lane3-r3-acceptance.json` is still absent. Independent CLI/model/docs work is done. Do not treat this r2 as official full-suite or new-wheel evidence.
