"""CLI entry (`iai`). Same agents as HTTP; a new Store per process, so discover
then replay in one invocation can share locators, but two separate `iai`
commands cannot.
"""

from __future__ import annotations

import argparse
import json

from interfaces_ai.agents.base import Store
from interfaces_ai.agents.discovery import DiscoveryAgent
from interfaces_ai.agents.escalation import EscalationAgent
from interfaces_ai.agents.replay import ReplayEngine
from interfaces_ai.config import get_settings
from interfaces_ai.observability import configure_logging
from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.canonical import Money, TransferIntent
from interfaces_ai.schema.registry import institutions, load_native


def main(argv: list[str] | None = None) -> int:
    configure_logging(get_settings().log_level)
    parser = argparse.ArgumentParser(prog="iai", description="interfaces.ai local sandbox CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("institutions", help="List mock financial institutions")

    show = sub.add_parser("canonical", help="Print canonical snapshot for a bank")
    show.add_argument("institution_id")

    disc = sub.add_parser("discover", help="Run discovery against one or all banks")
    disc.add_argument("institution_id", nargs="?")

    replay = sub.add_parser("replay", help="Replay a transfer intent")
    replay.add_argument("institution_id")
    replay.add_argument("from_account_id")
    replay.add_argument("to_account_id")
    replay.add_argument("amount")
    replay.add_argument("--memo", default="cli transfer")

    args = parser.parse_args(argv)

    if args.cmd == "institutions":
        for inst in institutions():
            print(f"{inst.id:10} {inst.name:28} {inst.extract_kind}")
        return 0

    if args.cmd == "canonical":
        native = load_native(args.institution_id)
        snapshot = get_adapter(args.institution_id).to_canonical(native)
        print(snapshot.model_dump_json(indent=2))
        return 0

    store = Store()
    discovery = DiscoveryAgent()
    escalation = EscalationAgent(store)
    engine = ReplayEngine(escalation)

    if args.cmd == "discover":
        ids = [args.institution_id] if args.institution_id else [i.id for i in institutions()]
        for institution_id in ids:
            report = discovery.discover(institution_id)
            store.add_discovery(report)
            case = escalation.maybe_open_for_discovery(report)
            print(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
            if case:
                print(f"escalated: {case.id} {case.summary}")
        return 0

    intent = TransferIntent(
        institution_id=args.institution_id,
        from_account_id=args.from_account_id,
        to_account_id=args.to_account_id,
        amount=Money(amount=args.amount),
        memo=args.memo,
    )
    # latest_discovery is None unless `discover` ran earlier in this same process.
    result = engine.replay(intent, store.latest_discovery(args.institution_id))
    print(result.model_dump_json(indent=2))
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
