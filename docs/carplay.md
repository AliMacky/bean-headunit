# CarPlay

CarPlay comes from a Carlinkit CPC200-CCPA, a USB dongle with its own Wi-Fi and Bluetooth. The dongle handles the CarPlay connection with the phone. My code talks to the dongle over USB, sends it settings and touches, and gets back video, audio and status messages.

So far, my Rust code can start a wireless CarPlay session with an iPhone and show the live video in `bean-ui`. It's a desk prototype, switched on with `BEAN_CARPLAY` and run as root. There's no touch or audio yet, and no way back to the Home screen without restarting.

## Trying it

The dongle needs root until a udev rule gives the `bean` user access, so stop the normal UI and run it by hand. `SLINT_SCALE_FACTOR` here suits my 1080p desk display:

```
cargo build --release -p bean-ui
sudo systemctl stop bean-ui
sudo SLINT_BACKEND=linuxkms SLINT_SCALE_FACTOR=1.8 BEAN_CARPLAY=1 ./target/release/bean-ui
```

Video should take over the screen about 10 seconds after the phone connects. Press Ctrl-C when you're done, then run `sudo systemctl start bean-ui`.

There's also a small test program that logs every message and saves the video to `/tmp/carplay.h264`:

```
cargo build --release -p bean-carplay
sudo ./target/release/bean-carplay
```

## How much to trust this

There's no official documentation for this protocol. Everything here comes from one of three places, and the tables say which:

- **Seen**: I saw it happen on my dongle with my code.
- **Reference**: it comes from reading [node-CarPlay](https://github.com/rhysmorgan134/node-CarPlay) (MIT licensed), but I haven't tested it myself.
- **Guess**: it fits what I saw, but nothing confirms it.

My dongle runs newer firmware than node-CarPlay was written for, so Reference entries may not all apply.

## Rules for the dongle

- Don't update its firmware without a specific reason. Some updates have broken open-source tools, and I don't know if this dongle can go back to an older version.
- Don't install the AutoKit app. CarPlay works without it.
- Don't mount, format or write to the small disk it can show up as. It usually appears as `sda`, but the name can change.

## My dongle

| Field | Value |
| --- | --- |
| USB ID | `1314:1521` (`1314:1520` is the other ID node-CarPlay supports) |
| Firmware | `2026.07.31.1733CHY` or `2026.07.31.1733OHY` |
| Product type | `A15W` |
| Hardware version | `YMA0-WN16-0003` |
| Supported links | HiCar, CarPlay, Android Auto |
| USB speed | High speed (USB 2) |
| `bcdDevice` | `4.09`, which isn't the firmware version |

The last part of the firmware string changes between connections, with no firmware update involved. I don't know why.

### USB interfaces

| Interface | Class | Endpoints | Use |
| --- | --- | --- | --- |
| 0 | Vendor specific (`0xFF`) | Bulk IN `0x81`, bulk OUT `0x01` | All CarPlay traffic |
| 1 | Mass storage (`0x08`) | Bulk IN `0x82`, bulk OUT `0x02` | An 8 MB virtual disk, which I don't use |

Interface 1 doesn't always appear, so only rely on interface 0.

### It restarts when nobody talks to it

With no program running, the dongle keeps disconnecting and coming back, and the USB device number goes up each time. The gaps between restarts varied: about 20 seconds apart at one point, and about 2 minutes on average over a longer stretch. With my program running and sending heartbeats, the disconnect count stayed flat for several minutes.

Two consequences:

- A program can start while the dongle is mid-restart and not find it. I've seen it take about 4 to 7 seconds to come back, so the code has to retry instead of crashing.
- Stopping the program probably ends the phone's session, because the heartbeats stop and the dongle restarts.

## Message format

Every message in both directions is a 16-byte header followed by a payload. Each header field is a little-endian `u32`:

| Bytes | Field | Value |
| --- | --- | --- |
| 0 to 3 | Magic | `0x55AA55AA` |
| 4 to 7 | Length | Payload size in bytes, not counting the header |
| 8 to 11 | Type | See [message types](#message-types) |
| 12 to 15 | Type check | The type with every bit flipped (`!type` in Rust) |

If the magic or the type check is wrong, we've lost our place in the stream, because nothing marks where the next message starts.

## Starting a session

This is the sequence that works, in order. It follows node-CarPlay, leaving out a few messages:

| Step | Type | Content |
| --- | --- | --- |
| 1 | `0x99` file | `/tmp/screen_dpi` = 160 |
| 2 | `0x01` Open | Width, height, fps, format, packetMax, iBoxVersion, phoneWorkMode (see below) |
| 3 | `0x99` file | `/tmp/night_mode` = 0 |
| 4 | `0x99` file | `/tmp/hand_drive_mode` = 0 (left-hand drive) |
| 5 | `0x99` file | `/tmp/charge_mode` = 1 |
| 6 | `0x19` box settings | JSON, see below |
| 7 | `0x08` command | 1000, Wi-Fi enable |
| 8 | `0x08` command | 25, 5 GHz Wi-Fi |
| 9 | `0x08` command | 7, use the car's microphone |
| 10 | `0x08` command | 23, send audio over USB |
| 11 | `0x08` command | 1002, Wi-Fi connect, 1 second later |
| After that | `0xAA` heartbeat | Empty, every 2 seconds |
| After that | `0x08` command | 12, ask for a frame, about every 6 seconds |

node-CarPlay's code says the frame command is for CarPlay, and it sends it every 5 seconds. My guess is that it asks for a new keyframe, and I picked 6 seconds only because it fits my heartbeat loop.

Before I added steps 1, 3 to 6, 9 and 10, Bluetooth connected but the session never got further. I also disconnected the phone from my car around the same time, so I don't know which change fixed it, or if only some of those messages are needed.

Left out on purpose:

- **Box name** (`/etc/box_name`): it goes under `/etc`, so it may be permanent.
- **`wifiPair`** (command 1012): node-CarPlay sends this if nothing connects after 15 seconds. Pairing worked without it.
- **USB reset before starting**: node-CarPlay does this. It hasn't been needed so far.

### Open payload

Seven `u32`s, little-endian, identified only by their position:

| Field | Value I send | Status |
| --- | --- | --- |
| width | 1024 | Seen: video comes back at this size |
| height | 560 | Seen: video comes back at this size |
| fps | 30 | Reference. Not confirmed, because video is sent mostly when the screen changes |
| format | 5 | Reference, meaning unknown |
| packetMax | 49152 | Reference |
| iBoxVersion | 2 | Reference |
| phoneWorkMode | 2 | Reference |

The dongle sends a 28-byte `0x01` back, probably echoing these (guess).

### Settings as files

Type `0x99` asks the dongle to write a small file. The layout is:

```
u32   name length, including the zero byte at the end
...   name, ending in a zero byte
u32   content length
...   content
```

A number is 4 little-endian bytes, and a boolean is the number 0 or 1. As far as I know, files under `/tmp` are gone after a restart, because `/tmp` is usually held in memory, but I haven't confirmed that on this dongle.

### Box settings

Type `0x19` carries JSON in both directions. I send:

```json
{"mediaDelay":300,"syncTime":1700000000,"androidAutoSizeW":1024,"androidAutoSizeH":560}
```

`syncTime` is the current Unix time in seconds.

The dongle sends two kinds back:

- **About itself:** `uuid`, `boxType`, `productType`, `hwVersion`, `WiFiChannel`, `ChannelList`, `supportLinkType`, and `DevList` (known phones, with their Bluetooth address, name, model and iOS version).
- **About the session:** `MDLinkType`, `MDModel`, `MDOSVersion`, `MDLinkVersion`, `btMacAddr`, `btName`, and `cpuTemp`. These repeat during connection, with the phone's details filled in once it's up.

These include personal details, like the phone's name and Bluetooth address, so be careful when pasting logs anywhere public.

## What a session looks like

From one run with a phone that was already paired, in seconds after finding the dongle:

| Time | Message | Meaning |
| --- | --- | --- |
| 0.0 | | Open sent |
| 0.1 | `0xCC` | Firmware version |
| 0.2 | `0x0D`, `0x0E` | Bluetooth and Wi-Fi names |
| 0.2 | Commands 1000, 1001, 7 | Wi-Fi on, auto-connect on, car mic |
| 0.2 | `0x19`, `0x01` | Dongle info, Open reply |
| 1.1 | Command 1003 | Scanning for a phone |
| 1.2 | `0x23` | Phone's Bluetooth address (trying to connect, guess) |
| 3.3 | `0x24`, command 1007, command 1004 | Bluetooth connected, device found |
| 4.2 | `0x02` | Phone plugged in |
| 5.1 | Command 1009 | Wi-Fi connected |
| 6.9 | `0x03` | Phase |
| 9.0 | Commands 4, 500 | 500 asks for video focus |
| 9.5 | `0x19`, `0xA3`, `0x03` | Phone details now filled in |
| 9.5 | `0x06` | First video |
| 10.9 | `0x25`, command 1008 | Bluetooth disconnected, which also happened in other working sessions |

That's about 10 seconds to first video on this run. The first working run took about 19 seconds. Command 1009 doesn't always show up: one working session never reported it.

### When a session gets stuck

Once, the phone said CarPlay was connected but video never came. The log repeated this cycle about every 30 to 40 seconds: `0x02` (plugged), a long wait, `0x03`, `0x04` (unplugged), then Bluetooth connecting again. Spotify and Maps didn't offer CarPlay either, probably because no real session had started.

Re-pairing didn't fix it. Turning the phone's Bluetooth and Wi-Fi off and on, making sure it wasn't connected to my car, and unplugging the dongle did. I don't know which of those mattered. The head unit will need a way to recover from this by itself, because replugging isn't an option in the car.

### Pairing a new phone

1. Start the program and leave it running.
2. Turn on the phone's Wi-Fi and Bluetooth.
3. In the phone's Bluetooth settings, choose the dongle (`AutoKit-` and a code). Confirm the pairing code.
4. Accept the CarPlay prompt if one appears.

After that, the dongle lists the phone in `DevList` and connects by itself. The dongle only appeared under the phone's CarPlay settings some of the time. If the phone is actively connected to a car, disconnect it first.

## Message types

| Type | Name | Direction | Payload | Status |
| --- | --- | --- | --- | --- |
| `0x01` | Open | Both | See above. The dongle has also sent a 0-byte one | Seen |
| `0x02` | Plugged | From dongle | 8 bytes: phone type, then Wi-Fi flag | Seen, fields are Reference |
| `0x03` | Phase | From dongle | 4 bytes, meaning unknown | Seen |
| `0x04` | Unplugged | From dongle | None | Reference |
| `0x05` | Touch | To dongle | See [touch](#touch) | Reference |
| `0x06` | Video | From dongle | See [video](#video) | Seen |
| `0x07` | Audio | Both | See [audio](#audio) | Reference |
| `0x08` | Command | Both | 4-byte command | Seen |
| `0x09` | Logo type | To dongle | 4 bytes | Reference |
| `0x0A` | Bluetooth address | From dongle | Text | Reference |
| `0x0C` | Bluetooth PIN | From dongle | Text | Reference |
| `0x0D` | Bluetooth name | From dongle | Text | Seen |
| `0x0E` | Wi-Fi name | From dongle | Text | Seen |
| `0x0F` | Disconnect phone | To dongle | | Reference |
| `0x12` | Paired list | From dongle | 1 byte with no phone known, 33 bytes with one | Seen, meaning is Reference |
| `0x14` | Manufacturer info | From dongle | 8 bytes | Reference |
| `0x15` | Close dongle | To dongle | | Reference |
| `0x17` | Multi-touch | To dongle | | Reference |
| `0x18` | HiCar link | From dongle | 113 bytes of text | Seen, meaning is Reference |
| `0x19` | Box settings | Both | JSON | Seen |
| `0x23` | Unknown | From dongle | Phone's Bluetooth address as text | Seen, meaning is a Guess |
| `0x24` | Unknown | From dongle | Phone's Bluetooth address, arrives with Bluetooth connected | Seen, meaning is a Guess |
| `0x25` | Unknown | From dongle | Empty | Seen |
| `0x26` | Unknown | From dongle | Empty | Seen |
| `0x2A` | Media data | From dongle | Song info or album art (one was 111 KB) | Seen, fields are Reference |
| `0x99` | File | To dongle | See above | Seen working |
| `0xA3` | Unknown | From dongle | 492 bytes, not decoded yet | Seen |
| `0xAA` | Heartbeat | To dongle | None | Seen working |
| `0xCC` | Software version | From dongle | 32 bytes: text, padded with zero bytes | Seen |

Phone types in `0x02`, from the reference: 1 Android mirror, 3 CarPlay, 4 iPhone mirror, 5 Android Auto, 6 HiCar.

## Commands

Type `0x08` carries one little-endian `u32`, in either direction.

These I've seen or sent:

| Value | Name | Direction | Status |
| --- | --- | --- | --- |
| 4 | Unknown | From dongle | Seen before video starts |
| 7 | Car microphone | Both | Seen |
| 12 | Frame | To dongle | Sent, effect unconfirmed |
| 23 | Audio transfer off (send audio over USB) | To dongle | Sent |
| 25 | 5 GHz Wi-Fi | To dongle | Sent |
| 500 | Request video focus | From dongle | Seen |
| 506 | Unknown | From dongle | Seen while using the phone during a session |
| 507 | Unknown | From dongle | Seen while using the phone during a session |
| 1000 | Wi-Fi enable | Both | Seen |
| 1001 | Auto-connect enable | From dongle | Seen |
| 1002 | Wi-Fi connect | To dongle | Sent |
| 1003 | Scanning for a device | From dongle | Seen |
| 1004 | Device found | From dongle | Seen |
| 1006 | Connect to device failed | From dongle | Seen once, after a failed attempt |
| 1007 | Bluetooth connected | From dongle | Seen |
| 1008 | Bluetooth disconnected | From dongle | Seen |
| 1009 | Wi-Fi connected | From dongle | Seen, not in every session |

These are from the reference and untested:

| Value | Name |
| --- | --- |
| 1, 2 | Start, stop recording audio |
| 3 | Host UI requested (the "My Car" button) |
| 5 | Siri |
| 15 | Box microphone |
| 16, 17 | Night mode on, off |
| 22 | Audio transfer on (phone sends audio directly to the car) |
| 24 | 2.4 GHz Wi-Fi |
| 100, 101 | Left, right |
| 104, 105 | Select down, up |
| 106 | Back |
| 113, 114 | Up, down |
| 200 | Home |
| 201, 202, 203 | Play, pause, play/pause |
| 204, 205 | Next, previous track |
| 300, 301 | Accept, reject call |
| 501 | Release video focus |
| 1005 | Device not found |
| 1010 | Wi-Fi disconnected |
| 1011, 1012 | Bluetooth pairing started, Wi-Fi pair |

The knob plan maps well onto these: play/pause, next, and Siri.

## Video

A video payload is a 20-byte header followed by the video stream:

| Bytes | Field | Status |
| --- | --- | --- |
| 0 to 3 | Width | Seen |
| 4 to 7 | Height | Seen |
| 8 to 11 | Flags | Reference, meaning unknown |
| 12 to 15 | Length | Reference |
| 16 to 19 | Unknown | Reference |
| 20 onward | H.264 | Seen |

`ffprobe` reports the saved stream as H.264 High profile, `yuvj420p`, at the size requested in Open. Cutting off the first 20 bytes of each message and joining the rest gave a file `ffmpeg` decoded with no errors.

The first message is small (190 to 200 bytes), and the first keyframe decoded to a black screen. Frames seem to arrive mostly when the screen changes, not at a steady rate. In the sessions so far, each message has decoded cleanly when fed to the decoder as one packet.

### Decoding on the Pi 5

As far as I can find, the Pi 5 has a hardware decoder for HEVC but not H.264. So the video gets decoded in software, unless the dongle turns out to have a way to send HEVC, which I haven't found.

I measured with `ffmpeg -threads 1` on a 194-frame capture at 1024x560: 0.513 s, or about 378 frames per second on one core. At 30 fps, that's about 8% of one core.

That capture was mostly low motion, so it's a best case. Live decoding in the test program averaged about 4 ms per frame.

With the video on screen in `bean-ui`, at 1024x560 on a 1080p display, CPU use of one core was:

| Screen | CPU | Frame rate |
| --- | --- | --- |
| Mostly still | 1 to 4% | Very low |
| Changing | 12 to 19% | About 7 fps |

If the cost scales with frame rate, a steady 30 fps would be about 65% of one core. That's only an estimate, because I can't drive the screen hard without touch yet. It's still enough margin that I don't need to chase HEVC.

FFmpeg warns `No accelerated colorspace conversion from yuv420p to rgb24`, so converting to RGB is probably a big part of that cost. If it becomes a problem, I'd try RGBA first, which may have a faster path, then sending the YUV frames to the GPU and converting them there. The `deprecated pixel format` warning is about how `yuvj420p` labels its color range, and shouldn't matter as long as colors look right.

### Getting it on screen

| Option | How it works | Why or why not |
| --- | --- | --- |
| Inside `bean-ui` (chosen) | A thread reads the dongle and decodes, and Slint draws each frame | Simplest, and overlays draw on top for free. A crash takes the UI down, and `Restart=always` brings it back. Each frame gets copied |
| Separate process | `bean-carplay` decodes and shares frames with the UI | Contains crashes, but it's a lot of plumbing for a benefit I don't need yet |
| Separate display layer | Video goes straight to a hardware plane | Cheapest per frame, but Slint currently owns the display, so it would be the hardest by far |

The USB and protocol code stays in its own crate with no UI code in it, so either of the other two options stays possible without rewriting it. The approach follows Slint's official [FFmpeg example](https://github.com/slint-ui/slint/tree/master/examples/ffmpeg), using the `ffmpeg-next` crate.

How a frame gets to the screen:

1. A thread in `bean-ui` reads messages from the dongle and skips everything but video.
2. `VideoDecoder` (`carplay/src/video.rs`) decodes the H.264 and converts it to RGB.
3. The thread copies the frame into a `SharedPixelBuffer`, row by row because FFmpeg can pad each row, and posts it to the UI thread. An `Image` can only be made on the UI thread, but the buffer can cross between threads.
4. The UI thread sets `carplay-frame` and `carplay-active`, and the skin draws the image over everything else, leaving 40 px at the top for a status strip.

Known limits of the prototype:

- If the UI falls behind, frames queue up and the picture lags. It should keep only the newest frame.
- The window is 1024 units wide, so on a screen with a different shape the background shows beside the video. That goes away on a 1024x600 screen at scale 1.

### Building with FFmpeg

On Pi OS, install FFmpeg's development libraries and `clang` (see [Pi setup](pi-setup.md#6-install-rust-and-get-this-repo)). Pi OS patches FFmpeg with extra pixel formats, so `carplay/Cargo.toml` turns on the crate's `rpi` feature for 64-bit ARM Linux only. Without it, the crate fails to compile there. On a Mac, use `brew install ffmpeg pkg-config`.

## Audio

Not tested yet. In the reference, an audio payload starts with a decode type (`u32`), a volume (`f32`) and an audio type (`u32`). What follows is either 16-bit PCM samples or a short control value, such as Siri or a phone call starting.

The same layout goes the other way for the microphone.

## Touch

Not tested yet. In the reference, a touch is type `0x05` with four little-endian `u32`s:

| Field | Value |
| --- | --- |
| Action | 14 down, 15 move, 16 up |
| X | 0 to 10000, as a fraction of the width |
| Y | 0 to 10000, as a fraction of the height |
| Flags | 0 |

## Open questions

- Which startup messages are really needed?
- What do types `0x23`, `0x24`, `0x25`, `0x26` and `0xA3` mean? What about commands 4, 506 and 507? They may come from the newer firmware.
- What does the end of the firmware string (`CHY`, `OHY`) mean?
- What do `format`, `iBoxVersion` and `phoneWorkMode` in Open do?
- Can the dongle send HEVC?
- Does the frame command do anything useful?
- How does it cope with a real screen at a steady frame rate, and on a real drive?
- What causes a stuck session, and how can the head unit recover without a replug?

## Credits

The protocol knowledge comes from [node-CarPlay](https://github.com/rhysmorgan134/node-CarPlay) by Rhys Morgan and its contributors (MIT). [LIVI](https://github.com/f-io/LIVI) was useful for its firmware table, but it's GPLv3, so none of its code is used here.
