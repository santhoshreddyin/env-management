"""Step-by-step textual narrative of an integration, generated from its hops (FR-8)."""

from collections.abc import Mapping, Sequence

from app.flows.schemas import HopIn, IntegrationIn


def _describe_hop(hop: HopIn, names: Mapping[str, str]) -> str:
    src = names.get(hop.from_system, hop.from_system)
    dst = names.get(hop.to_system, hop.to_system)
    reply = hop.direction == "reply"
    p = hop.protocol

    if p in ("REST", "SOAP"):
        text = f"{src} returns the {p} response to {dst}." if reply else f"{src} calls {dst} over {p}."
    elif p == "MQ":
        what = "reply message" if reply else "request message"
        if hop.queue_name:
            qm = f" (queue manager {hop.queue_manager})" if hop.queue_manager else ""
            text = f"{src} puts the {what} on queue {hop.queue_name}{qm} for {dst}."
        else:
            text = f"{src} sends the {what} to {dst} over MQ."
    else:
        how = "MFT" if p == "MFT" else "file transfer"
        text = f"{src} sends the reply file to {dst} by {how}." if reply else f"{src} transfers a file to {dst} by {how}."

    if hop.notes:
        text += f" Note: {hop.notes}"
    return text


def build_narrative(integration: IntegrationIn, hops: Sequence[HopIn], names: Mapping[str, str]) -> list[str]:
    up = names.get(integration.upstream_id, integration.upstream_id)
    down = names.get(integration.downstream_id, integration.downstream_id)
    article = "an" if integration.pattern == "async" else "a"
    intro = f"{integration.name} is {article} {integration.pattern} integration from {up} to {down}"
    if integration.journey:
        intro += f" for the {integration.journey} journey"
    lines = [intro + "."]

    ordered = sorted(hops, key=lambda h: h.sequence)
    lines += [f"Step {h.sequence}: {_describe_hop(h, names)}" for h in ordered]

    if ordered:
        requests = sum(1 for h in ordered if h.direction == "request")
        replies = len(ordered) - requests
        protocols = list(dict.fromkeys(h.protocol for h in ordered))
        noun = "hop" if len(ordered) == 1 else "hops"
        lines.append(
            f"In total the flow has {len(ordered)} {noun} ({requests} request, {replies} reply) "
            f"using {', '.join(protocols)}."
        )
    return lines
