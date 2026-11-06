use crate::protocol::{self, Message, cmd, msg, send, send_command, send_number};
use log::{error, info};
use nusb::MaybeFuture;
use nusb::io::EndpointRead;
use nusb::transfer::{Bulk, In, Out};
use std::io::{self, Write};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const VENDOR_ID: u16 = 0x1314;
const PRODUCT_IDS: [u16; 2] = [0x1520, 0x1521];

const ENDPOINT_OUT: u8 = 0x01;
const ENDPOINT_IN: u8 = 0x81;

pub struct Config {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
}

pub struct Dongle {
    reader: EndpointRead<Bulk>,
}

impl Dongle {
    pub fn connect(config: &Config) -> io::Result<Dongle> {
        let info = find_dongle()?;
        info!(
            "found dongle {:04x}:{:04x}",
            info.vendor_id(),
            info.product_id()
        );

        let device = info.open().wait()?;
        let interface = device.claim_interface(0).wait()?;

        let mut writer = interface.endpoint::<Bulk, Out>(ENDPOINT_OUT)?.writer(4096);
        let reader = interface.endpoint::<Bulk, In>(ENDPOINT_IN)?.reader(4096);

        start_session(&mut writer, config)?;

        thread::spawn(move || {
            if let Err(e) = heartbeat(&mut writer) {
                error!("heartbeat stopped: {e}");
            }
        });

        Ok(Dongle { reader })
    }

    pub fn read_message(&mut self) -> io::Result<Message> {
        protocol::read_message(&mut self.reader)
    }
}

fn find_dongle() -> io::Result<nusb::DeviceInfo> {
    loop {
        let found = nusb::list_devices()
            .wait()?
            .find(|d| d.vendor_id() == VENDOR_ID && PRODUCT_IDS.contains(&d.product_id()));

        match found {
            Some(dongle) => return Ok(dongle),
            None => {
                info!("waiting for dongle");
                thread::sleep(Duration::from_secs(1));
            }
        }
    }
}

fn start_session(writer: &mut impl Write, config: &Config) -> io::Result<()> {
    let fields: [u32; 7] = [config.width, config.height, config.fps, 5, 49152, 2, 2];
    let mut open = Vec::new();
    for field in fields {
        open.extend_from_slice(&field.to_le_bytes());
    }

    send_number(writer, "/tmp/screen_dpi", 160)?;
    send(writer, msg::OPEN, &open)?;
    send_number(writer, "/tmp/night_mode", 0)?;
    send_number(writer, "/tmp/hand_drive_mode", 0)?;
    send_number(writer, "/tmp/charge_mode", 1)?;

    let sync_time = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(io::Error::other)?
        .as_secs();
    let settings = format!(
        "{{\"mediaDelay\":300,\"syncTime\":{sync_time},\"androidAutoSizeW\":{width},\"androidAutoSizeH\":{height}}}",
        width = config.width,
        height = config.height,
    );
    send(writer, msg::BOX_SETTINGS, settings.as_bytes())?;

    send_command(writer, cmd::WIFI_ENABLE)?;
    send_command(writer, cmd::WIFI_5GHZ)?;
    send_command(writer, cmd::MIC)?;
    send_command(writer, cmd::AUDIO_OVER_USB)?;

    info!("session started");
    Ok(())
}

fn heartbeat(writer: &mut impl Write) -> io::Result<()> {
    thread::sleep(Duration::from_secs(1));
    send_command(writer, cmd::WIFI_CONNECT)?;

    let mut tick: u32 = 0;
    loop {
        send(writer, msg::HEARTBEAT, &[])?;
        if tick.is_multiple_of(3) {
            send_command(writer, cmd::FRAME)?;
        }
        tick = tick.wrapping_add(1);
        thread::sleep(Duration::from_secs(2));
    }
}
