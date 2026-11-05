# Setting up the Pi from scratch

This takes a blank microSD card to a Pi that boots fast, plays the boot splash, and then hands the screen to the head unit UI. It works on a Pi 4 or Pi 5, on Raspberry Pi OS Bookworm or Trixie. For why each step is here and what it saves, see [boot-time.md](boot-time.md).

You'll need:

- A Raspberry Pi 4 or 5, with its power supply
- A microSD card (16 GB or more)
- A screen with HDMI (and the right micro HDMI cable for the Pi)
- Another computer to flash the card and SSH in from

On a Pi 5, use the official 5V 5A (27 W) USB-C supply. A weaker one still boots, but the Pi then limits USB devices to 600 mA in total, which isn't enough once a CarPlay dongle and audio are plugged in. Give it a cooler too, since it slows itself down when it gets hot. Plug the screen into the micro HDMI port next to the power port (HDMI0).

## 1. Flash the SD card

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

## 2. First boot

Put the card in the Pi, plug in the screen, then power it on. The first boot takes a minute or two and may restart once while it expands the filesystem. Wait for a login prompt on the screen, then SSH in from your computer:

```
ssh <user>@<hostname>.local
```

If `.local` doesn't work on your network, find the Pi's IP address in your router's device list and use that instead. If you've reflashed the card before, clear the old fingerprint first with `ssh-keygen -R <hostname>.local`.

Check you got the right image. `uname -m` should print `aarch64`, and the screen should show a text login, not a desktop. `cat /etc/os-release` tells you which Debian release it's based on.

## 3. Update

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

## 4. Track system changes (recommended)

Every step after this one changes system config. [etckeeper](https://etckeeper.branchable.com/) turns `/etc` into a git repo, so each change has a history and you can undo one without remembering exactly what you ran. It also keeps file permissions and owners, which plain git doesn't, and commits on its own before and after every `apt install` or upgrade.

```
sudo apt install -y etckeeper
sudo git -C /etc log --oneline        # should show an initial commit
```

Steps 8 and 9 edit `/boot/firmware` instead of `/etc`, so give its two config files a small repo of their own:

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

## 5. Measure, then trim the boot

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

## 6. Install Rust and get this repo

The head unit is written in Rust and builds on the Pi itself. Install Rust with [rustup](https://rustup.rs), taking the default options:

```
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
```

Then the libraries the UI needs to draw straight to the screen and read input without a desktop. The last three are the GPU's OpenGL libraries, which Pi OS Lite doesn't include. Without them the UI still runs, but draws on the CPU, which is several times slower and uses a whole core:

```
sudo apt install -y build-essential pkg-config libudev-dev libinput-dev libxkbcommon-dev libgbm-dev libdrm-dev libfontconfig-dev libegl1 libegl-mesa0 libgles2
```

And the code:

```
git clone https://github.com/AliMacky/bean-headunit.git ~/bean-headunit
```

To try the animation over SSH, play it once and exit (make your terminal window wide):

```
SPLASH_ONCE=1 python3 ~/bean-headunit/splash/splash.py
```

## 7. Install the head unit

One script does the rest. Run it as your normal user, not with `sudo`. It asks for your password when it needs it.

```
~/bean-headunit/system/install.sh --sim
```

It:

- builds `bean-ui` and `bean-sim` and installs them to `/usr/local/bin`
- creates a `bean` system user to run them. It can't log in and is only allowed to use the screen, the GPU and input devices
- installs the splash to `/usr/local/share/bean-headunit/splash`
- creates `/etc/bean-headunit/bean.env` from `system/bean.env.example`, if you don't have one yet
- installs and enables the `bean-splash` and `bean-ui` services, plus `bean-sim` with `--sim`
- commits `/etc` if you set up etckeeper

`--sim` also starts the fake core at boot, so the UI has data to show at your desk. Leave it off once the real core exists. The first build takes a while; later runs are quick.

Then set your own values in the config. It's yours and stays on the Pi:

```
sudo nano /etc/bean-headunit/bean.env
```

| Setting | Default | What it does |
| --- | --- | --- |
| `BEAN_TITLE` | `MIATA` | Name in the UI's top bar |
| `BEAN_UNITS` | `f` | `f` for °F, `c` for °C |
| `SLINT_SCALE_FACTOR` | `1` | Scales the UI, which is designed for 1024x600. Around 1.8 fills a 1440p display |
| `SPLASH_TAGLINE` | `Mazda MX-5 Miata` | Line typed under the car on the splash |

Any splash setting from [splash.md](splash.md#settings) can go here too.

Turn off the login prompt on the Pi's screen, otherwise it draws over the splash. You can still log in on the Pi itself with Ctrl+Alt+F2, and SSH isn't affected.

```
sudo systemctl disable getty@tty1.service
sudo reboot
```

On boot, the splash plays, the car drives in and the tagline types out, and then the UI takes over. If the UI doesn't show up, `systemctl status bean-ui` and `journalctl -u bean-ui -b` say why. The journal should say `Using FemtoVG OpenGL renderer`. If it says `Software renderer`, the OpenGL libraries above are missing.

The UI needs a screen connected to start. Without one it keeps retrying, every 10 seconds at most, and comes up as soon as a screen appears.

To update later, pull and run the script again. It keeps your config and only replaces what it installed:

```
cd ~/bean-headunit && git pull && system/install.sh --sim
sudo systemctl restart bean-ui
```

## 8. Hide the boot text

By default you see a rainbow square and a wall of kernel messages before the splash. This turns them off so the splash is the first thing on screen. `cmdline.txt` has to stay on a single line, which is why this uses `sed` instead of editing it by hand. The first command makes a backup.

```
sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak
sudo sed -i 's/$/ quiet loglevel=3 logo.nologo vt.global_cursor_default=0 consoleblank=0/' /boot/firmware/cmdline.txt
echo "disable_splash=1" | sudo tee -a /boot/firmware/config.txt
sudo git -C /boot/firmware commit -am "Hide boot text"    # if you set up the repo in step 4
sudo reboot
```

## 9. Skip the initramfs (Trixie)

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

That's it. From now on the Pi boots straight into the splash and then the UI. To change how the splash looks or behaves, see [splash.md](splash.md).
