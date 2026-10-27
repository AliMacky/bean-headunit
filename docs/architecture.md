# Architecture

The head unit software is split into separate programs that talk over a local Unix socket, so the part that reads the car never depends on the part that draws the screen.

```
beand (the core, in the car)  ─┐                            ┌─▶ bean-ui + a skin   (the screen)
                               ├─▶ /tmp/bean.sock ──────────┼─▶ web dashboard      (later)
bean-sim (fake core, at desk) ─┘   length-prefixed          └─▶ dump               (debugging)
                                   MessagePack frames
```

Only one of `beand` and `bean-sim` runs at a time. Everything on the right side can't tell which one it's talking to.

## The pieces

| Piece | Crate | Status | What it does |
| --- | --- | --- | --- |
| Contract | `model/` (`bean-model`) | Started | The types and wire format every program shares |
| Fake core | `sim/` (`bean-sim`) | Working | Streams made-up car data, so the UI can be built without the car |
| Dump client | `model/examples/dump.rs` | Working | Connects and prints every message, for debugging |
| Logger | `log/` (`bean-log`) | Working | One log format for every program: time since start, level, and where the line came from |
| Core | `core/` (`beand`) | Planned | OBD, ignition and power, trip logging to SQLite, warnings, settings, later calls and the CarPlay host |
| UI | `ui/` (`bean-ui`) | Started | Rust and [Slint](https://slint.dev). Connects to the core and shows live values; loading a skin at runtime comes next |
| Skins | `skins/cluster/` | Planned | The current "90s cluster" design. Night and day and the accent color are settings inside it |
| Web dashboard | `web/` | Later | Trip history and diagnostics from another device |

Why separate processes: if the UI crashes or restarts, the core keeps logging and keeps checking warning thresholds. It also means the UI can be developed on a laptop against `bean-sim`, with nothing car-specific running.

Why skins: a skin is a folder of `.slint` files, tokens and fonts that binds to one Slint global holding all the car state, plus its callbacks. The UI shell loads it with the Slint interpreter, so a new look doesn't need a rebuild. The Slint global will be generated from `bean-model`, so the core, the UI and the skins can't drift apart.

## The contract

`bean-model` is the one place that defines what goes over the socket. The first slice is a single message type, `CarState`:

| Field | Type | Meaning |
| --- | --- | --- |
| `water_temp_c` | `Option<i16>` | Coolant temperature in °C |
| `rpm` | `Option<u16>` | Engine speed |
| `battery_v` | `Option<f32>` | Battery voltage, read by the OBD adapter |
| `obd_status` | `ObdStatus` | `NoAdapter`, `Connecting`, `NoResponse` or `Connected` |
| `theme` | `Theme` | `Night` or `Day` |

Rules it follows:

- Units are always metric. The skin converts to °F if that's what the user picked, so thresholds and trip logs in the core never depend on a display setting.
- A value the core doesn't have (OBD unplugged, a sensor the car doesn't support) is `None`, not 0. That keeps "0 rpm" and "no rpm reading" different. `obd_status` says why values are missing.
- Messages are [MessagePack](https://msgpack.org) with field names included (`rmp_serde::to_vec_named`). It's smaller and quicker to parse than JSON, and keeping the names means an older UI can still read messages from a newer core that added fields.
- `PROTOCOL_VERSION` goes up whenever a change would break older programs, like renaming or removing a field.

## Framing

A socket is a stream of bytes with no message boundaries, and MessagePack has no separator like the newline in JSON lines. So every message goes out as a 4-byte big-endian length, then that many bytes of MessagePack:

```
[ 00 00 00 46 ][ 70 bytes of MessagePack ][ 00 00 00 46 ][ 70 bytes ] ...
```

`write_frame` and `read_frame` in `bean-model` are the only code that does this, so every program frames messages the same way. Readers reject any length over `MAX_FRAME` (64 KB) before allocating, so a corrupt or hostile length can't make them try to allocate gigabytes. There's a test for that.

The socket lives at `/tmp/bean.sock` for now (`SOCKET_PATH`). On the Pi it will move to a proper runtime folder once the core runs as a systemd service.

## Threads, not async

`bean-sim` and the clients use plain blocking reads and writes, with one thread per client. It's simple, and nothing here needs more yet. If the core ends up juggling enough connections and devices, async Rust is an option later.

## The UI

`bean-ui` opens a fixed 1024x600 window, the size of the 7" screen it's designed for. For now the markup is built into the binary with Slint's `slint!` macro and shows water temp and rpm. Moving it out into `skins/cluster/` and loading it at runtime is the next step.

It runs on two threads:

- The main thread belongs to Slint's event loop, which draws the window and handles input. Slint's UI objects can only be touched from this thread, and Rust enforces that at compile time.
- A reader thread connects to the socket and reads frames. For each `CarState` it posts a small job back to the main thread (`upgrade_in_event_loop` on a weak handle to the window), and that job sets the window's properties. Slint's bindings then redraw whatever depends on them.

Each value the contract makes optional becomes two properties in the UI, a `-known` flag and the value, since Slint has no `Option`. Unknown values show as `--`, never as 0.

When the core isn't there, the UI stays up and keeps trying:

- The reader thread tries to connect once a second until it works.
- If the core goes away mid-stream, the UI shows NO CORE and clears every value to `--`, since a frozen reading is worse than no reading. Then it goes back to retrying.
- Failed connects are logged once per kind of error, not every second, so the log stays readable.
- If the window is closed, the reader thread stops.

## Logging

Every program logs through the standard [`log`](https://docs.rs/log) crate's macros (`info!`, `warn!`, `error!`), and `bean-log` is the backend that decides what a line looks like. Each program calls `bean_log::init()` first thing in `main`. Lines go to stderr:

```
[   0.002] WARN  bean_ui: connect failed: No such file or directory (os error 2)
[   3.418] INFO  bean_ui: connected to /tmp/bean.sock
```

The time is seconds since that program started, which is handy for seeing how long startup steps take. The name after the level is the crate (or module) the line came from, filled in by the macro.

Levels mean the same thing everywhere: `error` when a program can't do its job, `warn` when something went wrong but it's handled (like the core going away), `info` for normal events worth seeing.

Program output isn't logging. The dump's `println!` of each state goes to stdout and stays that way.

On the Pi, each program will run as a systemd service, so the journal collects all their stderr in one place, and `journalctl -o short-monotonic` lines everything up by time since boot. Planned for `bean-log`: colors when stderr is a terminal, and systemd's level prefixes when it isn't, so the journal knows which lines are warnings and errors.

## Working on it

I write and test on a laptop and build on the Pi when something needs the real hardware. Before committing I run `cargo fmt` and `cargo clippy` along with `cargo test`.

What clients see when things go wrong:

- The core stops while a client is connected: `read_frame` fails with `UnexpectedEof`.
- A client starts and the core has never run: connecting fails with `NotFound`, because the socket file doesn't exist.
- A client starts after the core has stopped: connecting fails with `ConnectionRefused`, because the old socket file is still there with nothing listening. `bean-sim` removes the stale file when it starts.

The dump just exits on any of these. The UI handles all three the same way: show NO CORE and retry.
