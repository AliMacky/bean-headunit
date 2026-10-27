# bean-headunit

A homemade head unit for my 2001 Mazda Miata (NB, British Racing Green, his name is Mr. Bean), built on a Raspberry Pi.

I didn't want an off-the-shelf stereo. Outside of CarPlay their interfaces are bad, and the firmware is locked down, so you can't change anything. With a Pi underneath, it's just Linux, and I get to decide everything: what shows up when the car starts, when the screen turns on and off, what data from the car gets shown, and how the controls work.

So far the project is a stripped-down Raspberry Pi OS install, a custom boot animation, and the start of the Rust code for the head unit software. This README covers setting up the first two from a blank SD card, and building the code.

![The boot splash](splash/splash-preview-screen.gif)

## Where it's at

- [x] Pi OS Lite set up and trimmed for faster boot (4.8 s on the Pi 5, down from 23.5 s on a fresh Pi 4)
- [x] Boot splash: an ASCII animation of the car that plays from early in boot
- [ ] Head unit software in Rust: a core that reads the car and a Slint UI with swappable skins (started: the shared data contract)
- [ ] CarPlay through a USB CarPlay dongle, first with react-carplay, then a native client
- [ ] OBD2 over USB for engine codes and live data
- [ ] Physical controls in place of the ashtray: a volume knob (click to pause, double click to skip, hold for Siri), a USB-C port, and a screen-off switch
- [ ] Car power handling: ignition sense, safe shutdown, read-only root filesystem
- [ ] Later: an ESP32 with its own sensors for data OBD can't give

I started on a Pi 4 and moved to a Pi 5 running Raspberry Pi OS Trixie, which is what the final unit will use. For now it sits on my desk hooked up to a 1440p monitor until I pick the screen for the car.

## Boot time

Measured with `systemd-analyze`, booting from a microSD card. The Pi 4 ran Bookworm and the Pi 5 runs Trixie, with the same services turned off on both. The raw output for each step is in [`notes/`](notes/).

| Pi | Step | Kernel | Userspace | Total |
| --- | --- | --- | --- | --- |
| Pi 4 | Fresh Pi OS Lite | 2.3 s | 21.2 s | 23.5 s |
| Pi 4 | Unneeded services turned off | 2.3 s | 13.0 s | 15.3 s |
| Pi 5 | Fresh Pi OS Lite | 1.3 s | 13.5 s | 14.8 s |
| Pi 5 | Unneeded services turned off | 1.4 s | 3.4 s | 4.8 s |

On the Pi 4, most of what was left was NetworkManager connecting to Wi-Fi, which nothing on screen waits for. On the Pi 5 that takes about 1.1 s, and the whole userspace boot fits in 3.4 s. Either way, the splash starts as soon as the filesystems are mounted, before the network is up.

On the Pi 5, booting without the initramfs (step 9) brought the kernel phase from 1.4 s down to 0.7 s. The splash now starts about 2.7 s after the kernel does, compared to about 3.4 s before.

`systemd-analyze` only starts counting once the kernel is running, so it misses the firmware and bootloader, and the time the monitor takes to wake up. What actually matters in a car is the time from turning the key to seeing the car on screen, so I also time that with a stopwatch from plugging in power:

| Pi | Until the animation starts |
| --- | --- |
| Pi 4, 1080p monitor | about 21 s |
| Pi 5, 1440p monitor | 7 to 10 s |

## What's in here

```
bean-headunit/
  README.md
  Cargo.toml                 Rust workspace, lists the crates
  Cargo.lock                 exact dependency versions, shared by every crate
  model/                     bean-model: the data contract shared by the core, UI and sim
  sim/                       bean-sim: a fake core that streams made-up car data, for working without the car
  notes/                     boot time measurements
  splash/
    splash.py                plays the boot animation (plain Python, no packages)
    frames/                  the pre-rendered animation
    mrbean-splash.service    systemd unit that starts it at boot
    build_frames.py          renders the animation into frames/
    verify_frames.py         checks rendered frames for glitches
    preview_gif.py           makes a GIF from a frames file
    preview_screen.py        makes a GIF of the whole screen as the Pi shows it
```

## Setting it up from scratch

You'll need:

- A Raspberry Pi 4 or 5, with its power supply
- A microSD card (16 GB or more)
- A screen with HDMI (and the right micro HDMI cable for the Pi)
- Another computer to flash the card and SSH in from

On a Pi 5, use the official 5V 5A (27 W) USB-C supply. A weaker one still boots, but the Pi then limits USB devices to 600 mA in total, which isn't enough once a CarPlay dongle and audio are plugged in. Give it a cooler too, since it slows itself down when it gets hot. Plug the screen into the micro HDMI port next to the power port (HDMI0).

### 1. Flash the SD card

1. Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) on your computer and put the SD card in.
2. Device: your Pi model.
3. OS: Raspberry Pi OS (other) → Raspberry Pi OS Lite (64-bit). Make sure it says Lite. The default option at the top is the full desktop version, which you don't want here.
4. Storage: your SD card. Double-check you're not picking some other drive.
5. When it asks about OS customization, choose to edit the settings:
   - Hostname: whatever you want to call the head unit (I named mine after the car). This is how you'll find it on the network as `<hostname>.local`.
   - Username and password: your login. You'll need the password for `sudo`.
   - Wi-Fi: your network name (case sensitive), password, and country.
   - Locale: your timezone and keyboard layout.
   - Services: turn on SSH. Password login works. Public key login is safer and means you never type a password: paste in the contents of your computer's `~/.ssh/id_ed25519.pub` (run `ssh-keygen -t ed25519` first if you don't have one, but don't overwrite one you already have).
6. Write the card, then eject it.

### 2. First boot

Put the card in the Pi, plug in the screen, then power it on. The first boot takes a minute or two and may restart once while it expands the filesystem. Wait for a login prompt on the screen, then SSH in from your computer:

```
ssh <user>@<hostname>.local
```

If `.local` doesn't work on your network, find the Pi's IP address in your router's device list and use that instead. If you've reflashed the card before, clear the old fingerprint first with `ssh-keygen -R <hostname>.local`.

Check you got the right image. `uname -m` should print `aarch64`, and the screen should show a text login, not a desktop. `cat /etc/os-release` tells you which Debian release it's based on. This README works on both Bookworm and Trixie.

### 3. Update

```
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git
sudo reboot
```

Also worth checking once: `vcgencmd get_throttled` should say `throttled=0x0`. Anything else usually means the power supply isn't strong enough.

Update the bootloader now too, since step 5 turns off the service that checks for updates at boot:

```
sudo rpi-eeprom-update        # shows the current and latest versions
sudo rpi-eeprom-update -a     # installs the update, if there is one
sudo reboot
```

### 4. Track system changes (recommended)

Every step after this one changes system config. [etckeeper](https://etckeeper.branchable.com/) turns `/etc` into a git repo, so each change has a history and you can undo one without remembering exactly what you ran. It also keeps file permissions and owners, which plain git doesn't, and commits on its own before and after every `apt install` or upgrade.

```
sudo apt install -y etckeeper
sudo git -C /etc log --oneline        # should show an initial commit
```

The boot text change in step 8 edits `/boot/firmware` instead of `/etc`, so give its two config files a small repo of their own:

```
cd /boot/firmware
sudo git init
printf '*\n!.gitignore\n!cmdline.txt\n!config.txt\n' | sudo tee .gitignore
sudo git add -A && sudo git commit -m "Stock boot config"
cd ~
```

If git asks who you are, set a name and email for root with `sudo git config --global user.name "Your Name"` and `sudo git config --global user.email "you@example.com"`.

After each step, commit with a message:

```
sudo etckeeper commit "Trim boot services"
```

To undo a step later:

```
sudo git -C /etc log --oneline
sudo git -C /etc revert <commit>
sudo etckeeper init                   # restores permissions after a revert
sudo systemctl daemon-reload
```

`/etc` holds your Wi-Fi password, your password hash, and the Pi's SSH keys, so keep this repo on the Pi. For an off-Pi backup, image the whole SD card from your computer instead. You can flash the image back with Raspberry Pi Imager ("Use custom").

### 5. Measure, then trim the boot

See where you're starting from:

```
systemd-analyze
systemd-analyze blame | head -20
```

Service names can change between Pi OS releases, so check which of these your image has before turning anything off:

```
systemctl list-unit-files | grep -E 'wait-online|eeprom|e2scrub|cloud'
```

These services slow boot down without doing anything a car needs:

| Service | What it does | Why it can go |
| --- | --- | --- |
| `NetworkManager-wait-online` | Holds up boot until Wi-Fi connects | Nothing on screen needs the network first |
| `cloud-init` | Applies the Imager settings on first boot | It already did its job |
| `rpi-eeprom-update` | Checks for bootloader updates every boot | You can run it by hand now and then |
| `e2scrub_reap` | Filesystem housekeeping | Not needed at boot |

```
sudo systemctl disable NetworkManager-wait-online.service
sudo systemctl disable rpi-eeprom-update.service
sudo systemctl disable e2scrub_reap.timer e2scrub_reap.service
sudo touch /etc/cloud/cloud-init.disabled
sudo reboot
```

Then run `systemd-analyze` again to see the difference. If you set up etckeeper, commit: `sudo etckeeper commit "Trim boot services"`.

### 6. Get this repo

```
git clone https://github.com/AliMacky/bean-headunit.git ~/bean-headunit
```

To try the animation over SSH, play it once and exit (make your terminal window wide):

```
SPLASH_ONCE=1 python3 ~/bean-headunit/splash/splash.py
```

### 7. Install the boot splash

The service file has a placeholder, `@SPLASH_DIR@`, for where the splash lives. This fills it in and installs it:

```
sed "s#@SPLASH_DIR@#$HOME/bean-headunit/splash#" ~/bean-headunit/splash/mrbean-splash.service | sudo tee /etc/systemd/system/mrbean-splash.service > /dev/null
```

Then turn off the login prompt on the Pi's screen, otherwise it draws over the animation. You can still log in on the Pi itself with Ctrl+Alt+F2, and SSH isn't affected.

```
sudo systemctl disable getty@tty1.service
sudo systemctl daemon-reload
sudo systemctl enable --now mrbean-splash.service
```

It should start playing on the screen right away. With etckeeper: `sudo etckeeper commit "Install boot splash"`.

### 8. Hide the boot text

By default you see a rainbow square and a wall of kernel messages before the splash. This turns them off so the splash is the first thing on screen. `cmdline.txt` has to stay on a single line, which is why this uses `sed` instead of editing it by hand. The first command makes a backup.

```
sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak
sudo sed -i 's/$/ quiet loglevel=3 logo.nologo vt.global_cursor_default=0 consoleblank=0/' /boot/firmware/cmdline.txt
echo "disable_splash=1" | sudo tee -a /boot/firmware/config.txt
sudo git -C /boot/firmware commit -am "Hide boot text"    # if you set up the repo in step 4
sudo reboot
```

### 9. Skip the initramfs (Trixie)

Pi OS Trixie boots through an initramfs, a small temporary system that runs before the real one. The Pi kernel already has the drivers it needs to mount the SD card, so it doesn't need one. Bookworm didn't use one either. Skipping it cuts the kernel phase about in half, starts the splash about 0.7 s sooner, and gets rid of the two `e2fsck` lines the initramfs prints over the boot screen.

Check that your image uses one first:

```
grep -n auto_initramfs /boot/firmware/config.txt     # Trixie shows auto_initramfs=1
```

If it does:

```
sudo sed -i 's/^auto_initramfs=1/auto_initramfs=0/' /boot/firmware/config.txt
sudo git -C /boot/firmware commit -am "Boot without initramfs"
sudo reboot
```

You don't lose the filesystem check. The initramfs used to check the root partition before mounting it. Without it, the kernel mounts root read-only, systemd checks it (`systemd-fsck-root.service`), and then remounts it read-write, the same as on Bookworm. The check's output goes to the journal instead of the screen, so `journalctl -b -u systemd-fsck-root` shows it ran.

To undo it, run `sudo git -C /boot/firmware revert --no-edit HEAD` and reboot. If the Pi won't boot, put the card in your computer, open `config.txt` on the boot partition, and change `auto_initramfs=0` back to `1`.

That's it. From now on the Pi boots straight into the animation.

## The boot splash

The car slides in through a forest at night on a dirt road, brakes hard, stops in the middle of the screen, flashes its high beams, and the name slams in. Then it idles, with stars twinkling and headlights glowing, until the real UI takes over.

Everything on screen is text. The trees, stars, road, dust, and headlight beams are ASCII, and so is the car: its outlines are matched to the shapes of characters like `/ \ _ | ( )`. The Pi's console can't show braille, but normal terminals can, so over SSH the car is drawn in braille dots instead because it looks sharper.

All the drawing happens ahead of time in `build_frames.py`, so the Pi doesn't do any image work at boot. `splash.py` just loads one file and prints text, which lets it start very early.

### Making it yours

The name, timing, colors, and ASCII character sets are at the top of `build_frames.py` (`NAME = "MR. BEAN"`). The line under the animation is `TAGLINE` at the top of `splash.py`, and changing it doesn't need a rebuild. The car is traced from a side photo of an NB with the hardtop; changing its shape means editing the coordinates in the car section of `build_frames.py`.

Rebuilding is easiest on your own computer:

```
pip3 install pillow numpy pyte
cd splash
python3 build_frames.py                     # about a minute
python3 verify_frames.py frames/*.json      # check for glitches
python3 preview_screen.py screen.gif        # see the whole screen as the Pi will show it
```

Then commit the new `frames/*.json` and `git pull` on the Pi. You don't need to reinstall the service.

`preview_screen.py` assumes a 1080p screen (240 x 67 characters). For another size, pass it in: `python3 preview_screen.py screen.gif 320 90` for a 1440p screen. Run `stty size` on the Pi's own screen to see yours (it prints rows, then columns).

You don't have to rebuild for a different screen. `splash.py` reads the console size when it starts, picks the biggest car that fits, centers it, and fills the extra sky with stars. On a bigger screen the car just takes up less of it.

For a solid white car on the console instead of an ASCII one, build with `python3 build_frames.py --console-car blocks`.

### Settings

These are `Environment=` lines in `mrbean-splash.service`. After changing one, run the install command from step 7 again, then `sudo systemctl daemon-reload`.

| Setting | Default | What it does |
| --- | --- | --- |
| `SPLASH_PREROLL` | `2.0` | Seconds to hold the empty scene before the car drives in, so the screen has time to wake up |
| `SPLASH_WAIT_MAX` | `10` | Longest to wait for the screen to be ready before starting anyway |
| `SPLASH_STYLE` | auto | `half` for the console version, `braille` for the terminal version |
| `SPLASH_ONCE` | off | `1` exits after the intro instead of looping |

### Good to know

It looks different over SSH. Your terminal's font and colors are much softer than the Pi console's, which only has 16 harsh colors ("green" is bright green and "yellow" comes out orange). `preview_screen.py` is the closest thing to the real screen.

If the start gets cut off, your monitor is slow to wake up after the Pi switches video modes. Raise `SPLASH_PREROLL` to 3 or 4.

You might occasionally catch a tearing line. The Linux console has no vsync. The splash only redraws characters that changed and never clears a line, which hides almost all of it. A graphical UI won't have this.

The splash loops until something stops it. When there's a real UI, its service can stop the splash by adding `Conflicts=mrbean-splash.service` and `After=mrbean-splash.service` to its `[Unit]` section.

## The head unit software

This part is just getting started. The plan is two programs that talk over a local Unix socket:

- `beand`, the core. It owns everything that has to keep working no matter what's on screen: reading OBD, ignition and power, trip logging, warnings and settings, and later calls and CarPlay.
- `bean-ui`, the screen. It's built with [Slint](https://slint.dev) and loads its look from a skin folder when it starts, so the current design is just one skin of many.

Keeping them apart means a UI crash doesn't stop logging or warnings. A third program, `sim`, pretends to be the core with fake data, so I can build the UI at my desk without the car.

Everything is Rust, in one Cargo workspace. So far it has two crates:

- `model/` (`bean-model`): the contract between the core and everything that talks to it. Every program uses these same types, so they can't drift apart.
- `sim/` (`bean-sim`): listens on the socket and sends every client a fake car state 10 times a second. The engine warms up to 90 °C, rpm swings between idle and 4000, and the battery wobbles around 14.1 V. Every client sees the same fake car.

The first slice of the contract covers water temp, rpm, battery voltage, OBD status, and the day/night theme. It follows a few rules:

- Units are always metric. The skin converts to °F if that's what the user picked.
- A value the core doesn't have (OBD unplugged, a sensor the car doesn't support) is unknown, not 0. In Rust that's an `Option`, so "0 rpm" and "no rpm reading" stay different things.
- Messages are [MessagePack](https://msgpack.org) with field names included. It's smaller and quicker to parse than JSON, and keeping the names means an older UI can still read messages from a newer core.
- On the socket, each message is a 4-byte big-endian length followed by the MessagePack bytes, up to 64 KB. MessagePack has no separator between messages the way JSON lines has newlines, so the length is how a reader knows where one ends.
- The socket lives at `/tmp/bean.sock` for now (`SOCKET_PATH` in `bean-model`), so every program finds it in the same place.
- `PROTOCOL_VERSION` in `model/src/lib.rs` goes up whenever a change would break older programs.

### Building it

I write and test on my laptop and build on the Pi when something needs the real hardware. Install Rust with [rustup](https://rustup.rs):

```
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Then from the repo root:

```
cargo build
cargo test
```

Before committing I also run `cargo fmt` (formatting) and `cargo clippy` (lints).

To start the fake core:

```
cargo run -p bean-sim
```

It prints `sim listening on /tmp/bean.sock` and runs until you press Ctrl+C. To check that it's sending, run `nc -U /tmp/bean.sock` in another terminal. You'll see the raw MessagePack scroll by as mostly garbage, with the field names readable in between.
