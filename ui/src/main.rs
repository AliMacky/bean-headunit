use std::os::unix::net::UnixStream;
use std::thread;

use bean_model::{CarState, SOCKET_PATH, read_frame};

slint::slint! {
    export component MainWindow inherits Window {
        width: 1024px;
        height: 600px;
        title: "bean-ui";
        background: #000000;

        in property <bool> water-known;
        in property <int> water-c;
        in property <bool> rpm-known;
        in property <int> rpm;

        VerticalLayout {
            alignment: center;
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

fn main() -> Result<(), slint::PlatformError> {
    let window = MainWindow::new()?;
    let weak = window.as_weak();

    thread::spawn(move || {
        let mut socket = match UnixStream::connect(SOCKET_PATH) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("connect failed: {e}");
                return;
            }
        };

        println!("connected to {SOCKET_PATH}");

        loop {
            let state = match read_frame(&mut socket) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("read failed: {e}");
                    return;
                }
            };

            if weak
                .upgrade_in_event_loop(move |w| apply(&w, &state))
                .is_err()
            {
                return;
            }
        }
    });

    window.run()
}
