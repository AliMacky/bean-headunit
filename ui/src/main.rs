use bean_carplay::dongle::{Config, Dongle, Outgoing};
use bean_carplay::protocol::{TouchAction, msg, touch_payload};
use bean_carplay::video::{RgbFrame, VideoDecoder};
use log::{info, warn};
use slint::{Image, Rgb8Pixel, SharedPixelBuffer};
use std::io;
use std::os::unix::net::UnixStream;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use bean_model::{CarState, SOCKET_PATH, Theme, read_frame};

slint::include_modules!();

type TouchSlot = Arc<Mutex<Option<Sender<Outgoing>>>>;

struct Latest<T> {
    value: Mutex<Option<T>>,
    wake_pending: AtomicBool,
}

impl<T> Latest<T> {
    fn new() -> Self {
        Latest {
            value: Mutex::new(None),
            wake_pending: AtomicBool::new(false),
        }
    }

    fn put(&self, value: T) -> bool {
        *self.value.lock().expect("latest lock poisoned") = Some(value);
        !self.wake_pending.swap(true, Ordering::AcqRel)
    }

    fn take(&self) -> Option<T> {
        self.wake_pending.store(false, Ordering::Release);
        self.value.lock().expect("latest lock poisoned").take()
    }
}

fn apply(window: &MainWindow, state: &CarState) {
    let car = window.global::<Car>();
    car.set_night(state.theme == Theme::Night);

    if let Some(t) = state.water_temp_c {
        car.set_water_known(true);
        car.set_water_c(i32::from(t));
    } else {
        car.set_water_known(false);
    }

    if let Some(r) = state.rpm {
        car.set_rpm_known(true);
        car.set_rpm(i32::from(r));
    } else {
        car.set_rpm_known(false);
    }

    if let Some(r) = state.battery_v {
        car.set_volts_known(true);
        car.set_volts(r);
    } else {
        car.set_volts_known(false);
    }
}

fn set_disconnected(window: &MainWindow) {
    let car = window.global::<Car>();

    car.set_connected(false);
    car.set_water_known(false);
    car.set_volts_known(false);
    car.set_rpm_known(false);
}

fn to_pixel_buffer(frame: &RgbFrame) -> SharedPixelBuffer<Rgb8Pixel> {
    let mut buffer = SharedPixelBuffer::<Rgb8Pixel>::new(frame.width, frame.height);
    let row_len = frame.width as usize * 3;

    let source_rows = frame.data.chunks_exact(frame.stride);
    let dest_rows = buffer.make_mut_bytes().chunks_exact_mut(row_len);
    for (source, dest) in source_rows.zip(dest_rows) {
        dest.copy_from_slice(&source[..row_len]);
    }

    buffer
}

fn send_touch(slot: &TouchSlot, kind: TouchKind, x: f32, y: f32) {
    let action = match kind {
        TouchKind::Down => TouchAction::Down,
        TouchKind::Move => TouchAction::Move,
        TouchKind::Up => TouchAction::Up,
    };

    let guard = slot.lock().expect("touch slot lock poisoned");
    if let Some(sender) = guard.as_ref() {
        let _ = sender.send((msg::TOUCH, touch_payload(action, x, y)));
    }
}

fn run_carplay(window: slint::Weak<MainWindow>, slot: &TouchSlot) -> Result<(), String> {
    let config = Config {
        width: 1280,
        height: 750,
        fps: 30,
    };
    let mut dongle = Dongle::connect(&config).map_err(|e| e.to_string())?;
    let mut decoder = VideoDecoder::new().map_err(|e| e.to_string())?;
    *slot.lock().expect("touch slot lock poisoned") = Some(dongle.sender());

    info!("CarPlay connected");
    let mut frames: u64 = 0;
    let latest: Arc<Latest<SharedPixelBuffer<Rgb8Pixel>>> = Arc::new(Latest::new());

    loop {
        let message = dongle.read_message().map_err(|e| e.to_string())?;
        if message.msg_type != msg::VIDEO {
            continue;
        }

        let result = decoder.decode(&message.payload, |frame| {
            frames += 1;
            if frames % 100 == 1 {
                info!(
                    "decoded frame {frames}: {}x{}, stride {}",
                    frame.width, frame.height, frame.stride
                );
            }

            let buffer = to_pixel_buffer(&frame);
            if latest.put(buffer) {
                let latest = Arc::clone(&latest);
                let sent = window.upgrade_in_event_loop(move |w| {
                    if let Some(buffer) = latest.take() {
                        w.set_carplay_frame(Image::from_rgb8(buffer));
                        w.set_carplay_active(true);
                    }
                });
                if let Err(e) = sent {
                    warn!("couldn't send frame to the UI: {e}");
                }
            }
        });
        if let Err(e) = result {
            warn!("decode error: {e}");
        }
    }
}

fn tell_systemd_ready() {
    if let Err(e) = sd_notify::notify(&[sd_notify::NotifyState::Ready]) {
        warn!("couldn't tell systemd we're ready: {e}");
    }
}

fn main() -> Result<(), slint::PlatformError> {
    bean_log::init().expect("Failed to init logger");

    let window = MainWindow::new()?;

    let mut logged = false;
    let notifier = window.window().set_rendering_notifier(move |state, _| {
        if !logged && matches!(state, slint::RenderingState::AfterRendering) {
            info!("first frame drawn");
            logged = true;
            tell_systemd_ready();
        }
    });
    if let Err(e) = notifier {
        warn!("can't detect the first frame: {e}");
        tell_systemd_ready();
    }

    if let Ok(title) = std::env::var("BEAN_TITLE") {
        window.global::<Settings>().set_title(title.into());
    }
    if let Ok(units) = std::env::var("BEAN_UNITS") {
        match units.as_str() {
            "f" | "imperial" => window.global::<Settings>().set_fahrenheit(true),
            "c" | "metric" => window.global::<Settings>().set_fahrenheit(false),
            other => warn!("unknown BEAN_UNITS {other:?}, keeping the default"),
        }
    }

    if std::env::var_os("BEAN_CARPLAY").is_some() {
        let slot: TouchSlot = Arc::new(Mutex::new(None));

        let ui_slot = Arc::clone(&slot);
        window.on_carplay_touch(move |kind, x, y| send_touch(&ui_slot, kind, x, y));

        let weak = window.as_weak();
        thread::spawn(move || {
            loop {
                if let Err(e) = run_carplay(weak.clone(), &slot) {
                    warn!("CarPlay stopped: {e}");
                }
                *slot.lock().expect("touch slot lock poisoned") = None;
                thread::sleep(Duration::from_secs(1));
            }
        });
    }

    let weak = window.as_weak();

    thread::spawn(move || {
        let mut last_err: Option<io::ErrorKind> = None;

        loop {
            let mut socket = match UnixStream::connect(SOCKET_PATH) {
                Ok(s) => s,
                Err(e) => {
                    if Some(e.kind()) != last_err {
                        warn!("connect failed: {e}. Waiting for reconnection...");
                    }
                    last_err = Some(e.kind());
                    thread::sleep(Duration::from_secs(1));
                    continue;
                }
            };

            last_err = None;

            if weak
                .upgrade_in_event_loop(|w| {
                    w.global::<Car>().set_connected(true);
                })
                .is_err()
            {
                return;
            }

            info!("connected to {SOCKET_PATH}");

            loop {
                let state = match read_frame(&mut socket) {
                    Ok(s) => s,
                    Err(e) => {
                        warn!("read failed: {e}");
                        break;
                    }
                };

                if weak
                    .upgrade_in_event_loop(move |w| apply(&w, &state))
                    .is_err()
                {
                    return;
                }
            }

            if weak
                .upgrade_in_event_loop(|w| set_disconnected(&w))
                .is_err()
            {
                return;
            }

            thread::sleep(Duration::from_secs(1));
        }
    });

    window.run()
}
