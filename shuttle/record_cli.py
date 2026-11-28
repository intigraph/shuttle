"""Key registration display and foreign-run import commands."""
import json
from pathlib import Path

from . import export as export_mod, model, signing, state


def cmd_keys_init(args) -> int:
    wf = export_mod.workflow_iri(args.workflow) if args.workflow else f"{export_mod.entity_ns()}workflow:*"
    print(f"agent:      {args.agent}")
    print(f"public key: {signing.public_key_hex(args.agent)}")
    print()
    print("# Registration Turtle — review and load into the IDENTITY graph")
    print("# (dataKind=identity, never frozen) YOURSELF; shuttle never")
    print("# registers its own keys. The trust root stays human-owned.")
    print(signing.registration_turtle(args.agent, wf))
    return 0


def import_run(args, defs, runs) -> int:
    """Import a foreign transitions JSONL (the NeuralAmplifier export shape)
    as a complete run: define (if carried), start, then each transition
    signed by the IMPORTING agent — the importer attests the mapping, since
    the original system did not sign shuttle messages."""
    lines = [json.loads(x) for x in Path(args.file).read_text().splitlines() if x.strip()]
    if not lines:
        raise model.WorkflowError(f"{args.file} holds no records")
    for rec in lines:
        t = rec.get("type")
        if t == "define":
            if rec["name"] not in defs:
                model.parse_definition(rec)  # refuse before recording
                state.append(rec)
        elif t == "start":
            if rec["run"] in runs:
                raise model.WorkflowError(f"run '{rec['run']}' already exists; refusing to merge histories")
            start = {**rec, "agent": args.agent}
            start["signature"] = signing.sign_start(start, export_mod.run_iri(rec["run"]))
            state.append(start)
        elif t == "transition":
            at = rec["at"]
            sig = signing.sign_transition(
                args.agent, export_mod.run_iri(rec["run"]), rec["step"], rec["from"], rec["to"], at
            )
            state.append({**rec, "agent": args.agent, "signature": sig})
        else:
            raise model.WorkflowError(f"unknown record type {t!r} in {args.file}")
    print(f"imported {len(lines)} records from {args.file} (signed by '{args.agent}')")
    return 0


