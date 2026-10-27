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
| Core | `core/` (`beand`) | Planned | OBD, ignition and power, trip logging to SQLite, warnings, settings, later calls and the CarPlay host |
| UI | `ui/` (`bean-ui`) | Planned | Rust and [Slint](https://slint.dev). Connects to the core and loads a skin at runtime |
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

## Working on it

I write and test on a laptop and build on the Pi when something needs the real hardware. Before committing I run `cargo fmt` and `cargo clippy` along with `cargo test`.

What the dump shows when things go wrong, which the UI will need to handle:

- The core stops while a client is connected: `read_frame` fails with `UnexpectedEof`.
- A client starts before the core: connecting fails with `ConnectionRefused`.

Right now the dump just exits. The UI will show a disconnected state and keep retrying.
