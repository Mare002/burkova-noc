#!/usr/bin/env python3
"""Classify each voicebot call into exactly one outcome label.

Usage:
    python classify.py data/transcripts.jsonl > predictions_night1.csv
    python classify.py data/transcripts.jsonl -o predictions.csv
    type data\\transcripts.jsonl | python classify.py - > predictions.csv

Night 2 runs on data where "something may have changed". Everything that
protects against that lives in this file, in three layers:

1. Input layer (read_records): JSONL or one JSON array, UTF-8 with/without
   BOM, blank/corrupt lines, wrapper keys ("events"/"turns"/...), missing
   call_id. Every input record yields exactly one output row.
2. Normalisation layer (normalise_event): renamed fields ("ts", "tool",
   "result_status"...), renamed event types ("assistant", "function_call",
   "end"...), renamed tools ("check_outage" -> get_outage by keyword),
   timestamps as numbers, strings, ISO dates or missing.
3. Decision layer (classify): uses only structured events, never bot
   wording, and treats unknown statuses by meaning (timeout/5xx = tool
   failure, any other non-ok = "nothing found").

Anything unexpected is counted and printed to stderr as a WARNING, so drift
is visible live without crashing or dropping a call.

Rule of thumb from the brief: label what the caller LEFT WITH, not what broke
and was recovered along the way.
"""
import csv
import json
import sys
from collections import Counter
from datetime import datetime

LABELS = (
    "KNOWN_OUTAGE_INFORMED", "TICKET_CREATED", "TRANSFERRED", "TRANSFER_FAILED",
    "API_ERROR", "ADDRESS_NOT_UNDERSTOOD", "OUT_OF_SCOPE", "ENDED_EARLY",
)
FALLBACK_LABEL = "ENDED_EARLY"

drift = Counter()  # unexpected things seen, reported on stderr

# ---------------------------------------------------------------- aliases ---
# First key found wins. Canonical name is first in each tuple.
FIELD_ALIASES = {
    "type":   ("type", "event", "event_type", "kind", "role"),
    "t":      ("t", "ts", "time", "time_s", "offset", "offset_s", "timestamp", "at"),
    "name":   ("name", "tool", "tool_name", "function", "fn"),
    "status": ("status", "result_status", "state", "outcome", "code"),
    "result": ("result", "data", "response", "output", "payload"),
    "by":     ("by", "ended_by", "party", "initiator", "who"),
    "text":   ("text", "utterance", "content", "message"),
}
RECORD_EVENT_KEYS = ("events", "turns", "messages", "log", "transcript", "items")
RECORD_ID_KEYS = ("call_id", "callId", "id", "call")

TYPE_ALIASES = {
    "bot": {"bot", "assistant", "agent", "voicebot", "system_message", "tts"},
    "caller": {"caller", "user", "customer", "human", "asr"},
    "tool_call": {"tool_call", "function_call", "tool_use", "tool_request", "call_tool"},
    "tool_result": {"tool_result", "function_result", "tool_response", "tool_output"},
    "transfer": {"transfer", "handoff", "hand_off", "escalation", "escalate", "warm_transfer"},
    "route": {"route", "redirect", "routing", "referral", "refer"},
    "hangup": {"hangup", "hang_up", "end", "call_end", "end_call", "disconnect", "ended"},
}
TYPE_LOOKUP = {alias: canon for canon, aliases in TYPE_ALIASES.items() for alias in aliases}

HANGUP_SIDE = {
    "bot": "bot", "assistant": "bot", "agent": "bot", "voicebot": "bot",
    "system": "system", "platform": "system", "dispatch": "system",
    "caller": "caller", "user": "caller", "customer": "caller", "human": "caller",
}

OK = {"ok", "success", "succeeded", "found", "done", "completed", "200", "201", "true"}
TRANSFER_OK = {"connected", "answered", "accepted", "ok", "success", "bridged", "completed"}
# resolve_address "nothing found" statuses we already know (others still work,
# they only add a warning).
ADDRESS_MISS = {"no_match", "ambiguous", "not_found", "no_result", "no_results",
                "multiple", "multiple_matches", "low_confidence", "partial", "empty"}
KNOWN_FAILURES = {"timeout", "error", "queue_full"}
OUTCOME_TOOLS = {"get_outage", "create_ticket"}


def norm(s):
    return str(s).strip().lower() if s is not None else ""


def pick(d, field):
    for key in FIELD_ALIASES[field]:
        if key in d:
            if key != FIELD_ALIASES[field][0]:
                drift[f"field_alias:{key}->{field}"] += 1
            return d[key]
    return None


def canon_tool(name):
    """Map a tool name to its role by keyword, so renames keep working."""
    n = norm(name)
    if n in ("get_outage", "create_ticket", "resolve_address"):
        return n
    if not n:
        return ""
    if "ticket" in n or "incident" in n or ("report" in n and "outage" not in n):
        role = "create_ticket"
    elif "outage" in n or "oms" in n or "fault" in n:
        role = "get_outage"
    elif "address" in n or "geocod" in n or "location" in n or "resolve" in n:
        role = "resolve_address"
    else:
        drift[f"unknown_tool:{n}"] += 1
        return n
    drift[f"tool_alias:{n}->{role}"] += 1
    return role


def parse_t(v):
    """Seconds as float. Accepts numbers, numeric strings, ISO datetimes."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.strip():
        s = v.strip()
        try:
            return float(s)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def tool_status(raw, e):
    """Status string; infer it when the field is missing."""
    st = norm(pick(e, "status"))
    if st:
        return st
    if isinstance(raw, dict) and raw.get("error"):
        return "error"
    if e.get("error"):
        return "error"
    if e.get("ok") is False or e.get("success") is False:
        return "error"
    drift["status_missing_inferred_ok"] += 1
    return "ok"


def normalise_event(e):
    """Return a canonical event dict, or None for unusable items."""
    if not isinstance(e, dict):
        drift["event_not_object"] += 1
        return None
    raw_type = norm(pick(e, "type"))
    typ = TYPE_LOOKUP.get(raw_type)
    if typ is None:
        # e.g. {"role": "tool", ...} or unknown types: guess from content
        if raw_type in ("tool", "function") and pick(e, "status") is not None:
            typ = "tool_result"
        elif raw_type in ("tool", "function"):
            typ = "tool_call"
        else:
            drift[f"unknown_event:{raw_type}"] += 1
            typ = raw_type or "unknown"
    elif raw_type != typ:
        drift[f"type_alias:{raw_type}->{typ}"] += 1
    out = {"type": typ, "_t_raw": pick(e, "t")}
    if typ in ("tool_call", "tool_result"):
        out["name"] = canon_tool(pick(e, "name"))
    if typ == "tool_result":
        res = pick(e, "result")
        out["result"] = res
        out["status"] = tool_status(res, e)
    if typ in ("transfer", "route"):
        out["status"] = norm(pick(e, "status"))
        out["target"] = norm(e.get("target") or e.get("to") or e.get("destination"))
    if typ == "hangup":
        out["by"] = norm(pick(e, "by"))
    return out


def prepare(events):
    """Normalise and order events; every event gets a numeric 't'."""
    if not isinstance(events, list):
        drift["events_not_list"] += 1
        return []
    evs = [x for x in (normalise_event(e) for e in events) if x is not None]
    ts = [parse_t(x["_t_raw"]) for x in evs]
    if evs and all(t is not None for t in ts):
        for x, t in zip(evs, ts):
            x["t"] = t
        return sorted(evs, key=lambda x: x["t"])  # stable: ties keep file order
    if evs:
        drift["bad_or_missing_t_used_file_order"] += 1
    for i, x in enumerate(evs):  # trust file order (brief: events are in time order)
        x["t"] = float(i)
    return evs


# --------------------------------------------------------------- decision ---
def outage_known(result):
    """get_outage result -> True (known outage), False (none), None (unclear)."""
    if isinstance(result, list):
        return bool(result)
    if not isinstance(result, dict):
        return None
    for key in ("outage_id", "outageId", "outage", "id"):
        if key in result:
            return bool(result[key])
    for key in ("outages", "items", "incidents"):
        if key in result:
            return bool(result[key])
    for key in ("known", "has_outage", "outage_known", "found"):
        if key in result:
            return bool(result[key])
    if result.get("eta") or result.get("status_text"):
        return True
    return None


def is_tool_failure(st):
    """Infrastructure failure (as opposed to a semantic 'nothing found')."""
    return (st in ("timeout", "error", "unavailable", "rate_limited", "cancelled",
                   "failed", "failure", "exception", "false")
            or "timeout" in st or "timed_out" in st or "error" in st
            or "unavailable" in st or "fail" in st
            or st.startswith(("5", "http_5", "http5", "429", "http_429")))
    # 404 / other 4xx are left out on purpose: for resolve_address a 404 means
    # "address not found", which is an address problem, not a broken tool.


def classify(events):
    events = prepare(events)

    hangup_t = None
    hangup_by = ""
    for e in events:
        if e["type"] == "hangup":
            hangup_t, hangup_by = e["t"], e.get("by", "")
            break
    if hangup_t is None:
        drift["no_hangup_event"] += 1
        hangup_t = float("inf")

    bot_times = [e["t"] for e in events if e["type"] == "bot"]

    def live(e):  # happened while the caller was still on the line
        return e["t"] <= hangup_t

    def bot_spoke_after(t):
        return any(t <= b <= hangup_t for b in bot_times)

    pending = {}            # tool name -> t of unanswered call
    informed = False        # caller heard a known-outage status/ETA
    # Ticket created counts even if the result came after the caller hung up:
    # the ticket exists and a technician gets dispatched, which is the outcome
    # that matters (unlike an outage status nobody heard). Not seen in night 1.
    ticket = False
    transfer = None         # "ok" | "failed"
    routed = False
    tool_error = False      # tool failed or never answered
    addr_tries = addr_miss = 0
    addr_ok = False         # resolver returned an id
    addr_confirmed = False  # we moved on to get_outage with it

    for e in events:
        typ = e["type"]
        name = e.get("name", "")
        st = e.get("status", "")

        if typ == "tool_call":
            pending[name] = e["t"]
            if name == "resolve_address":
                addr_tries += 1
            elif name == "get_outage":
                addr_confirmed = True

        elif typ == "tool_result":
            pending.pop(name, None)
            if name == "resolve_address":
                if st in OK:
                    addr_ok = True
                elif is_tool_failure(st):
                    if live(e):
                        tool_error = True
                    if st not in KNOWN_FAILURES:
                        drift[f"resolve_status:{st}"] += 1
                else:  # any other non-ok answer = address not determined
                    addr_miss += 1
                    if st not in ADDRESS_MISS:
                        drift[f"resolve_status:{st}"] += 1
            elif name == "get_outage":
                addr_confirmed = True  # result without a logged call still counts
                if st in OK:
                    known = outage_known(e.get("result"))
                    if known is None:
                        drift["get_outage_unclear_result"] += 1
                    if known and live(e) and bot_spoke_after(e["t"]):
                        informed = True
                else:
                    if st not in KNOWN_FAILURES:
                        drift[f"get_outage_status:{st}"] += 1
                    tool_error = True  # also counts if it arrives after hangup
            elif name == "create_ticket":
                if st in OK:
                    ticket = True
                else:
                    if st not in KNOWN_FAILURES:
                        drift[f"create_ticket_status:{st}"] += 1
                    tool_error = True
            # other tools (send_sms, ...) do not change the caller's outcome

        elif typ == "transfer":
            if st in TRANSFER_OK:
                transfer = "ok"
            elif st == "" and transfer is None:
                drift["transfer_without_status"] += 1  # attempt only, no outcome yet
            elif st not in ("", "initiated", "ringing", "started", "pending"):
                transfer = "failed"
                if st not in ("queue_full", "timeout"):
                    drift[f"transfer_status:{st}"] += 1

        elif typ == "route":
            # a "route" to dispatch is really a transfer outcome
            if "dispatch" in e.get("target", ""):
                drift["route_to_dispatch"] += 1
                transfer = "ok" if st in TRANSFER_OK or not st else "failed"
            else:
                routed = True

    # An outcome tool still waiting when the call ended = the caller got
    # nothing because the API was too slow (matches the labeled sample).
    if any(n in OUTCOME_TOOLS for n in pending):
        tool_error = True
    # A transfer that was announced but never resolved before hangup.
    if transfer is None and any(e["type"] == "transfer" for e in events):
        transfer = "failed"

    # Priority = what the caller walked away with.
    if transfer == "ok":
        return "TRANSFERRED"
    # A failed transfer followed by a fallback ticket leaves the caller with a
    # ticket, so the ticket wins over TRANSFER_FAILED.
    if ticket:
        return "TICKET_CREATED"
    if transfer == "failed":
        return "TRANSFER_FAILED"
    if informed:
        return "KNOWN_OUTAGE_INFORMED"
    if routed:
        return "OUT_OF_SCOPE"
    if tool_error:
        return "API_ERROR"
    # Address phase failed: resolver missed, or returned an id the caller
    # rejected, and we never got as far as checking outages.
    if addr_tries and not addr_confirmed and (addr_miss or addr_ok):
        side = HANGUP_SIDE.get(hangup_by)
        if side is None and hangup_by:
            drift[f"hangup_by:{hangup_by}"] += 1  # unknown -> caller side
        # caller hung up after only one miss -> they left early, bot did not give up
        if addr_tries >= 2 or side in ("bot", "system"):
            return "ADDRESS_NOT_UNDERSTOOD"
    return "ENDED_EARLY"


# ------------------------------------------------------------------ input ---
def record_id(rec, n):
    if isinstance(rec, dict):
        for k in RECORD_ID_KEYS:
            if rec.get(k) not in (None, ""):
                if k != "call_id":
                    drift[f"id_alias:{k}"] += 1
                return str(rec[k])
    drift["missing_call_id"] += 1
    return f"line-{n}"


def record_events(rec):
    if isinstance(rec, list):  # a bare list of events
        drift["record_is_event_list"] += 1
        return rec
    if not isinstance(rec, dict):
        return None
    for k in RECORD_EVENT_KEYS:
        if k in rec:
            if k != "events":
                drift[f"events_alias:{k}"] += 1
            return rec[k]
    drift["record_without_events"] += 1
    return []


def read_records(path):
    """Yield (n, record_or_None). JSONL or a single JSON array; BOM tolerant."""
    f = sys.stdin if path == "-" else open(path, encoding="utf-8-sig", errors="replace")
    with f:
        text = f.read()
    stripped = text.lstrip("﻿ \t\r\n")
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
            drift["input_is_json_array"] += 1
            for n, rec in enumerate(data, 1):
                yield n, rec
            return
        except json.JSONDecodeError:
            pass  # maybe JSONL whose first line is an array; fall through
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip().lstrip("﻿")
        if not line:
            continue
        try:
            yield n, json.loads(line)
        except json.JSONDecodeError:
            drift["corrupt_line"] += 1
            yield n, None


def main(argv):
    args = [a for a in argv if a not in ("-o",)]
    out_path = argv[argv.index("-o") + 1] if "-o" in argv else None
    if out_path:
        args.remove(out_path)
    path = args[0] if args else "data/transcripts.jsonl"

    if out_path:
        sink = open(out_path, "w", encoding="utf-8", newline="")
    else:
        try:  # identical bytes on Windows and Linux: UTF-8, LF line endings
            sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        except (AttributeError, ValueError):
            pass
        sink = sys.stdout

    out = csv.writer(sink, lineterminator="\n")
    out.writerow(["call_id", "label"])
    counts, seen = Counter(), set()
    for n, rec in read_records(path):
        cid = record_id(rec, n)
        if cid in seen:
            drift["duplicate_call_id"] += 1
        seen.add(cid)
        try:
            evs = record_events(rec)
            label = classify(evs) if evs is not None else FALLBACK_LABEL
        except Exception as exc:  # last resort: never drop a call
            drift[f"classify_error:{type(exc).__name__}"] += 1
            label = FALLBACK_LABEL
        if label not in LABELS:
            drift[f"bad_label:{label}"] += 1
            label = FALLBACK_LABEL
        counts[label] += 1
        out.writerow([cid, label])
    if out_path:
        sink.close()

    print(f"classified {sum(counts.values())} calls: {dict(counts)}", file=sys.stderr)
    if drift:
        print("WARNING unexpected inputs (labels still produced, check these):",
              file=sys.stderr)
        for k, v in drift.most_common():
            print(f"  {v:>7}  {k}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
