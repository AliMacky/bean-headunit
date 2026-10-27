use log::{info, warn};
use std::io;
use std::os::unix::net::{UnixListener, UnixStream};
use std::thread;
use std::time::{Duration, Instant};

use bean_model::{CarState, ObdStatus, SOCKET_PATH, Theme, write_frame};

fn main() -> io::Result<()> {
    bean_log::init().expect("Failed to init logger");

    let _ = std::fs::remove_file(SOCKET_PATH);
    let listener = UnixListener::bind(SOCKET_PATH)?;
    info!("sim listening on {SOCKET_PATH}");

    let start = Instant::now();
    for stream in listener.incoming() {
        let stream = stream?;
        info!("client connected");
        thread::spawn(move || serve(stream, start));
    }
    Ok(())
}

fn serve(mut stream: UnixStream, start: Instant) {
    loop {
        let t = start.elapsed().as_secs_f32();
        let state = fake_state(t);
        if write_frame(&mut stream, &state).is_err() {
            warn!("client disconnected");
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn fake_state(t: f32) -> CarState {
    CarState {
        water_temp_c: Some((20.0 + t * 3.0).min(90.0) as i16),
        rpm: Some((2400.0 + 1600.0 * (t * 0.5).sin()) as u16),
        battery_v: Some(14.1 + 0.2 * t.sin()),
        obd_status: ObdStatus::Connected,
        theme: Theme::Night,
    }
}
