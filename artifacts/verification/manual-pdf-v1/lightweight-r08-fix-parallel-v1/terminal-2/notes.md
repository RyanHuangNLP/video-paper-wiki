# Terminal 2 r08 mixed-link regression notes

Independent pytest CLI runner. Same assertions for old and new verifier.

- Old verifier `51d67390e22dc3c21f2f4f85b12a9ab78d8c583eb3242f4c8e7c81248661f743`: 3 mixed cases failed (exit 0 / ok=true); 4 controls/identity passed.
- T1 verifier `1ca5f342517294c1d5ed3ed3974585bc6ede410a15b08d78f84f6ae285120197`: 7 passed. Mixed reports have ok=false and errors naming the bad source href.
- Tests invoke `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python -B <verifier> --workspace --output --report`. argv script equals --verifier.
- Product src and T1 script were not edited. files=[].
