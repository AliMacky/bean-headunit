use log::{info, warn};
use std::io;
use std::os::unix::net::UnixStream;
use std::thread;
use std::time::Duration;

use bean_model::{CarState, SOCKET_PATH, Theme, read_frame};

slint::include_modules!();

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

fn main() -> Result<(), slint::PlatformError> {
    bean_log::init().expect("Failed to init logger");

    let window = MainWindow::new()?;

    let mut logged = false;
    let notifier = window.window().set_rendering_notifier(move |state, _| {
        if !logged && matches!(state, slint::RenderingState::AfterRendering) {
            info!("first frame drawn");
            logged = true;
        }
    });
    if let Err(e) = notifier {
        warn!("can't detect the first frame: {e}");
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
