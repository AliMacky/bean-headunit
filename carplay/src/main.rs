use bean_carplay::dongle::{Config, Dongle};
use bean_carplay::protocol::msg;
use ffmpeg::codec;
use ffmpeg::util::frame::Video as VideoFrame;
use ffmpeg_next as ffmpeg;
use log::{debug, info, warn};
use std::fs::File;
use std::io::Write;
use std::time::{Duration, Instant};

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

    ffmpeg::init().expect("couldn't start FFmpeg");
    let h264 = ffmpeg::decoder::find(codec::Id::H264).expect("no H.264 decoder");
    let mut decoder = codec::Context::new_with_codec(h264)
        .decoder()
        .video()
        .expect("couldn't open decoder");

    let mut frame = VideoFrame::empty();
    let mut frames_decoded: u64 = 0;
    let mut decode_time = Duration::ZERO;

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
                let video = &payload[VIDEO_HEADER_LEN..];
                video_file.write_all(video).expect("couldn't write video");

                let packet = ffmpeg::Packet::copy(video);
                let start = Instant::now();
                if let Err(e) = decoder.send_packet(&packet) {
                    warn!("decode error: {e}");
                }
                while decoder.receive_frame(&mut frame).is_ok() {
                    frames_decoded += 1;
                    if frames_decoded % 100 == 1 {
                        info!(
                            "frame {frames_decoded}: {}x{} {:?}, average decode {:?}",
                            frame.width(),
                            frame.height(),
                            frame.format(),
                            decode_time / frames_decoded.max(1) as u32
                        );
                    }
                }
                decode_time += start.elapsed();
            }
            msg::AUDIO | msg::HEARTBEAT | msg::MEDIA => {
                debug!("type {msg_type:#04x}, {length} bytes")
            }
            _ => info!("type {msg_type:#04x}, {length} bytes"),
        }
    }
}
