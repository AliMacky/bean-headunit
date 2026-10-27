# Boot time

In a car, the time that matters is from turning the key to seeing something on screen. This is how far that's come, and what did and didn't help. The steps themselves are in [pi-setup.md](pi-setup.md), and the raw `systemd-analyze` output for each measurement is in [`notes/`](../notes/).

## Measurements

Measured with `systemd-analyze`, booting from a microSD card. The Pi 4 ran Bookworm and the Pi 5 runs Trixie, with the same services turned off on both.

| Pi | Step | Kernel | Userspace | Total |
| --- | --- | --- | --- | --- |
| Pi 4 | Fresh Pi OS Lite | 2.3 s | 21.2 s | 23.5 s |
| Pi 4 | Unneeded services turned off | 2.3 s | 13.0 s | 15.3 s |
| Pi 5 | Fresh Pi OS Lite | 1.3 s | 13.5 s | 14.8 s |
| Pi 5 | Unneeded services turned off | 1.4 s | 3.4 s | 4.8 s |

On the Pi 4, most of what was left was NetworkManager connecting to Wi-Fi, which nothing on screen waits for. On the Pi 5 that takes about 1.1 s, and the whole userspace boot fits in 3.4 s. Either way, the splash starts as soon as the filesystems are mounted, before the network is up.

On the Pi 5, booting without the initramfs ([step 9](pi-setup.md#9-skip-the-initramfs-trixie)) brought the kernel phase from 1.4 s down to 0.7 s. The splash now starts about 2.7 s after the kernel does, compared to about 3.4 s before.

## Power on to animation

`systemd-analyze` only starts counting once the kernel is running, so it misses the firmware and bootloader, and the time the screen takes to wake up. So I also time it with a stopwatch from plugging in power:

| Pi | Until the animation starts |
| --- | --- |
| Pi 4, 1080p monitor | about 21 s |
| Pi 5, 1440p display | 7 to 10 s |

The Pi 5 number was measured before the splash's preroll dropped from 2.0 s to 0.3 s and before the initramfs change, so it should be lower now. I'll remeasure on the real car screen, since how fast the screen wakes up is a big part of it.

## What helped

- Turning off services a car doesn't need at boot (`NetworkManager-wait-online`, `cloud-init`, `rpi-eeprom-update`, `e2scrub_reap`). This was the biggest single win: Pi 5 userspace went from 13.5 s to 3.4 s.
- Starting the splash as soon as local filesystems are mounted, without waiting for the network or the normal boot ordering.
- Skipping the initramfs, which halved the kernel phase and removed the two `e2fsck` lines it printed over the boot screen.
- A shorter preroll (`SPLASH_PREROLL` 0.3 s). The preroll is the empty scene held before the car drives in, so a slow screen doesn't miss the start. It's tuned for my current display and needs a recheck on the real one.

## Tried and dropped

- Changing the splash service's dependencies. It broke things, so it was taken back out of main.
- A custom kernel boot logo. There's no framebuffer early enough for it to show up, so it saved nothing.
- Shipping frame 0 pre-rendered so something appears instantly. The animation file already loads in about 0.1 s, so there was nothing to gain.
- Redirecting `fsck` output to hide the boot-screen lines. They turned out to come from the initramfs, so skipping the initramfs fixed it instead.

## Ideas for later

- The splash still waits for the boot partition's filesystem check, which takes about 0.65 s.
- `DISABLE_HDMI=1` in the bootloader EEPROM config, which skips the bootloader's own HDMI output.
