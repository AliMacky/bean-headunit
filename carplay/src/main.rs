use bean_carplay::dongle::{Config, Dongle};
use bean_carplay::protocol::msg;
use log::{debug, info};
use std::fs::File;
use std::io::Write;

const VIDEO_PATH: &str = "/tmp/carplay.h264";
const VIDEO_HEADER_LEN: usize = 20;

fn main() {
    bean_log::init().expect("Failed to init logger");

    let config = Config {
        width: 1024,
        height: 560,
        fps: 30,
    };
    let mut dongle = Dongle::connect(&config).expect("couldn't connect to dongle");

    let mut video_file = File::create(VIDEO_PATH).expect("couldn't create video file");
    let mut video_count: u64 = 0;

    loop {
        let message = dongle.read_message().expect("couldn't read message");
        let msg_type = message.msg_type;
        let payload = message.payload;
        let length = payload.len();

        match msg_type {
            msg::SOFTWARE_VERSION
            | msg::BLUETOOTH_NAME
            | msg::WIFI_NAME
            | msg::BOX_SETTINGS
            | msg::PHONE_CONNECTING
            | msg::PHONE_CONNECTED => {
                let text = String::from_utf8_lossy(&payload);
                info!("type {msg_type:#04x}: {}", text.trim_end_matches('\0'));
            }
            msg::COMMAND => {
                let value = u32::from_le_bytes(payload[0..4].try_into().unwrap());
                info!("command {value}");
            }
            msg::VIDEO => {
                video_file
                    .write_all(&payload[VIDEO_HEADER_LEN..])
                    .expect("couldn't write video");
                video_count += 1;
                if video_count % 100 == 1 {
                    let width = u32::from_le_bytes(payload[0..4].try_into().unwrap());
                    let height = u32::from_le_bytes(payload[4..8].try_into().unwrap());
                    info!("video message {video_count}: {width}x{height}, {length} bytes");
                }
            }
            msg::AUDIO | msg::HEARTBEAT | msg::MEDIA => {
                debug!("type {msg_type:#04x}, {length} bytes")
            }
            _ => info!("type {msg_type:#04x}, {length} bytes"),
        }
    }
}
