# Slip

Telegram hides tool calls. The agent can write a file and you only see
"done". Slip appends the writes and sends from that turn onto the final
reply, from the hooks, not from what the model claimed.

Conduit and Desktop already show the tool stream. So does the CLI.
Slip stays off there.

## What you get

A Telegram turn that wrote `/tmp/slip-demo.txt` ends like this:

```
done

slip
wrote /tmp/slip-demo.txt (12 bytes)
```

A `read_file` of that path does not add a line. A failed or blocked
write does not add a line. `send_message` lists the target, never the
body.

## What it records

| Call | On the slip |
| --- | --- |
| `write_file` (ok) | `wrote <path> (N bytes)` |
| `patch` (ok) | `patched <path>` |
| `send_message` send | `sent to <target>` |
| `memory` add/replace/remove | `wrote memory` |
| `skill_manage` | `changed skill <name>` |
| `cronjob_manage` | `changed cron` |

Everything else is ignored, including reads, `send_message` list/react,
and any call with status `error` or `blocked`. Cap is 12 lines, then
`+N more`.

## How it works

`post_tool_call` appends a line to an in-memory list keyed by
`session_id`. `transform_llm_output` dumps that list under the reply
once per turn, then clears it. `pre_llm_call` clears it at the start
of the next turn.

It does not set `hold_stream`. A bug here cannot withhold the reply.
Hermes takes the first non-empty `transform_llm_output` string, so if
another plugin already rewrote the reply, slip is skipped for that
turn.

No network, no disk, no credentials.

Quiet platforms (`cli`, `tui`, `desktop`, `acp`, `conduit`): the list
is left unused and no footer is appended.

## Install

```
hermes plugins install k1ng0mar/hermes-slip --enable
```

Or copy this directory to `~/.hermes/plugins/slip/` and run
`hermes plugins enable slip`. Restart the gateway if one is already
running and did not hot-reload hooks.

## Tests

```
python3 -m unittest discover -s test -v
```

16 tests, stdlib only.

## Demo

From Telegram, not Conduit and not Desktop: ask the agent to write
`/tmp/slip-demo.txt`. The reply should end with the `slip` block
above. Then `read_file` that path. No new slip line.

## Limits

Terminal commands are not parsed, so a `cat > file` via `terminal`
will not show up. Bytes come from the `content` argument on
`write_file`, not from the disk. Concurrent sessions in one process
are isolated by `session_id`; a missing id shares one bucket.
