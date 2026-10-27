use log::{info, warn};
use std::io;
use std::os::unix::net::UnixStream;
use std::thread;
use std::time::Duration;

use bean_model::{CarState, SOCKET_PATH, read_frame};

slint::slint! {
    export component MainWindow inherits Window {
        width: 1024px;
        height: 600px;
        title: "bean-ui";
        background: #000000;

        in property <bool> connected;
        in property <bool> water-known;
        in property <int> water-c;
        in property <bool> rpm-known;
        in property <int> rpm;

        VerticalLayout {
            alignment: center;
            Text {
                text: root.connected ? "" : "NO CORE";
                color: #E0A030;
                font-size: 48px;
                horizontal-alignment: center;
            }
            Text {
                text: root.water-known ? "WATER: " + root.water-c + "°C" : "WATER: --";
                color: #C9A26B;
                font-size: 48px;
                horizontal-alignment: center;
            }
            Text {
                text: root.rpm-known ? "RPM: " + root.rpm : "RPM: ----";
                color: #C9A26B;
                font-size: 48px;
                horizontal-alignment: center;
            }
        }
    }
}

fn apply(window: &MainWindow, state: &CarState) {
    if let Some(t) = state.water_temp_c {
        window.set_water_known(true);
        window.set_water_c(i32::from(t));
    } else {
        window.set_water_known(false);
    }

    if let Some(r) = state.rpm {
        window.set_rpm_known(true);
        window.set_rpm(i32::from(r));
    } else {
        window.set_rpm_known(false);
    }
}

fn set_disconnected(window: &MainWindow) {
    window.set_connected(false);
    window.set_water_known(false);
    window.set_rpm_known(false);
}

fn main() -> Result<(), slint::PlatformError> {
    bean_log::init().expect("Failed to init logger");

    let window = MainWindow::new()?;
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
                    w.set_connected(true);
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
