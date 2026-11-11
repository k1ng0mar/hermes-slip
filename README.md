# Slip

On Telegram and Conduit, Hermes hides tool calls. The agent can write a
file and you only see "done". Slip appends a short mutation list the
hooks actually observed.

Desktop and the CLI already show tools, so slip stays out of those
surfaces.

## How it works

- `post_tool_call` records successful `write_file` and `patch` calls,
  and `send_message` sends (not list/react). Reads never appear. Failed
  or blocked calls never appear. Message bodies are never copied onto
  the slip.
- `transform_llm_output` appends the list to the final reply, once per
  turn, then clears it. It does not use `hold_stream`, so a bug here
  cannot withhold the reply. `pre_llm_call` also clears at the start of
  the next turn.

The counter is keyed by `session_id`. No network, no disk, no credentials.

Hermes runs `transform_llm_output` as first non-empty string wins. If
another plugin already rewrote the reply, slip is skipped for that turn.

## Install

Copy this directory to `~/.hermes/plugins/slip/`, then:

```
hermes plugins enable slip
```

Restart the gateway if one is already running.

## Tests

```
python3 -m unittest discover -s test -v
```

15 tests, stdlib only.

## Demo

On Telegram or Conduit: ask the agent to write `/tmp/slip-demo.txt`.
The reply should end with:

```
slip
wrote /tmp/slip-demo.txt (N bytes)
```

A `read_file` of that path must not add a line.
