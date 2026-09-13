"""Register the bounded discovery commands in the existing JSON-envelope CLI."""
from video_paper_wiki.envelope import emit_success


def _run(args):
    from video_paper_wiki_research import discovery
    action = args.discovery_action
    values = {k: v for k, v in vars(args).items() if k not in {"command", "discovery_action", "handler"}}
    return emit_success("discovery." + action, getattr(discovery, action)(**values))


def register_commands(subparsers):
    parser = subparsers.add_parser("discovery", allow_abbrev=False)
    actions = parser.add_subparsers(dest="discovery_action", required=True)
    flags = {
        "init": [("config-input", True)], "plan": [("specs-input", False)],
        "observe": [("request", True), ("observation-input", True)],
        "context": [], "finish": [("assessment-input", True)], "status": [], "resume": [],
        "control": [("action", True), ("event-id", True), ("user-text", True), ("source", True), ("recorded-at", True)],
        "decide": [("candidate-set", True), ("candidate-key", True), ("action", True), ("selected-arxiv", False),
                   ("event-id", True), ("user-text", True), ("source", True), ("recorded-at", True)],
        "handoff": [("decision", True)], "render": [],
    }
    for action, options in flags.items():
        leaf = actions.add_parser(action, allow_abbrev=False)
        leaf.add_argument("--session", required=True)
        for name, required in options:
            leaf.add_argument("--" + name, required=required, default=None)
        leaf.set_defaults(handler=_run)
