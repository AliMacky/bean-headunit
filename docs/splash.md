# The boot splash

![The boot splash](../splash/splash-preview-screen.gif)

The car slides in through a forest at night on a dirt road, brakes hard, stops in the middle of the screen, flashes its high beams, and the name slams in. Then it idles, with stars twinkling and headlights glowing, until the real UI takes over.

Everything on screen is text. The trees, stars, road, dust, and headlight beams are ASCII, and so is the car: its outlines are matched to the shapes of characters like `/ \ _ | ( )`. The Pi's console can't show braille, but normal terminals can, so over SSH the car is drawn in braille dots instead because it looks sharper.

All the drawing happens ahead of time in `build_frames.py`, so the Pi doesn't do any image work at boot. `splash.py` just loads one file and prints text, which lets it start very early.

To install it on a Pi, see [steps 6 to 8 of the setup guide](pi-setup.md#6-get-this-repo).

## Files

```
splash/
  splash.py                plays the boot animation (plain Python, no packages)
  frames/                  the pre-rendered animation
  mrbean-splash.service    systemd unit that starts it at boot
  build_frames.py          renders the animation into frames/
  verify_frames.py         checks rendered frames for glitches
  preview_gif.py           makes a GIF from a frames file
  preview_screen.py        makes a GIF of the whole screen as the Pi shows it
```

## Making it yours

The name, timing, colors, and ASCII character sets are at the top of `build_frames.py` (the name is `NAME`). The line under the animation is `TAGLINE` at the top of `splash.py`, and changing it doesn't need a rebuild. The car is traced from a side photo of an NB with the hardtop; changing its shape means editing the coordinates in the car section of `build_frames.py`.

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

## Settings

Set these as `Environment=` lines in `mrbean-splash.service`. After changing one, run the install command from [step 7](pi-setup.md#7-install-the-boot-splash) again, then `sudo systemctl daemon-reload`.

| Setting | Default | What it does |
| --- | --- | --- |
| `SPLASH_PREROLL` | `2.0` | Seconds to hold the empty scene before the car drives in, so the screen has time to wake up. The service file sets it to `0.3`, tuned for my current display |
| `SPLASH_WAIT_MAX` | `10` | Longest to wait for the screen to be ready before starting anyway |
| `SPLASH_STYLE` | auto | `half` for the console version, `braille` for the terminal version |
| `SPLASH_ONCE` | off | `1` exits after the intro instead of looping |

## Good to know

It looks different over SSH. Your terminal's font and colors are much softer than the Pi console's, which only has 16 harsh colors ("green" is bright green and "yellow" comes out orange). `preview_screen.py` is the closest thing to the real screen.

If the start gets cut off, your screen is slow to wake up after the Pi switches video modes. Raise `SPLASH_PREROLL` to 1, or up to 3 or 4 for a slow monitor.

You might occasionally catch a tearing line. The Linux console has no vsync. The splash only redraws characters that changed and never clears a line, which hides almost all of it. A graphical UI won't have this.

The splash loops until something stops it. When there's a real UI, its service can stop the splash by adding `Conflicts=mrbean-splash.service` and `After=mrbean-splash.service` to its `[Unit]` section.
