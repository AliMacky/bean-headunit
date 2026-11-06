use std::io::{self, Read, Write};

const MAGIC: u32 = 0x55AA55AA;

/// Message types. Names marked "guess" aren't confirmed, see docs/carplay.md.
pub mod msg {
    pub const OPEN: u32 = 0x01;
    pub const PLUGGED: u32 = 0x02;
    pub const PHASE: u32 = 0x03;
    pub const VIDEO: u32 = 0x06;
    pub const AUDIO: u32 = 0x07;
    pub const COMMAND: u32 = 0x08;
    pub const BLUETOOTH_NAME: u32 = 0x0D;
    pub const WIFI_NAME: u32 = 0x0E;
    pub const PAIRED_LIST: u32 = 0x12;
    pub const HICAR_LINK: u32 = 0x18;
    pub const BOX_SETTINGS: u32 = 0x19;
    /// Guess: the phone's Bluetooth address, when a connection starts.
    pub const PHONE_CONNECTING: u32 = 0x23;
    /// Guess: the phone's Bluetooth address, once Bluetooth has connected.
    pub const PHONE_CONNECTED: u32 = 0x24;
    pub const UNKNOWN_25: u32 = 0x25;
    pub const UNKNOWN_26: u32 = 0x26;
    pub const MEDIA: u32 = 0x2A;
    pub const FILE: u32 = 0x99;
    pub const UNKNOWN_A3: u32 = 0xA3;
    pub const HEARTBEAT: u32 = 0xAA;
    pub const SOFTWARE_VERSION: u32 = 0xCC;
}

pub mod cmd {
    pub const MIC: u32 = 7;
    pub const FRAME: u32 = 12;
    pub const AUDIO_OVER_USB: u32 = 23;
    pub const WIFI_5GHZ: u32 = 25;
    pub const WIFI_ENABLE: u32 = 1000;
    pub const WIFI_CONNECT: u32 = 1002;
}

pub struct Message {
    pub msg_type: u32,
    pub payload: Vec<u8>,
}

pub fn send(writer: &mut impl Write, msg_type: u32, payload: &[u8]) -> io::Result<()> {
    writer.write_all(&MAGIC.to_le_bytes())?;
    writer.write_all(&(payload.len() as u32).to_le_bytes())?;
    writer.write_all(&msg_type.to_le_bytes())?;
    writer.write_all(&(!msg_type).to_le_bytes())?;
    writer.write_all(payload)?;
    writer.flush()
}

pub fn send_command(writer: &mut impl Write, command: u32) -> io::Result<()> {
    send(writer, msg::COMMAND, &command.to_le_bytes())
}

pub fn send_file(writer: &mut impl Write, path: &str, content: &[u8]) -> io::Result<()> {
    let mut name = path.as_bytes().to_vec();
    name.push(0);

    let mut payload = Vec::new();
    payload.extend_from_slice(&(name.len() as u32).to_le_bytes());
    payload.extend_from_slice(&name);
    payload.extend_from_slice(&(content.len() as u32).to_le_bytes());
    payload.extend_from_slice(content);

    send(writer, msg::FILE, &payload)
}

pub fn send_number(writer: &mut impl Write, path: &str, value: u32) -> io::Result<()> {
    send_file(writer, path, &value.to_le_bytes())
}

pub fn read_message(reader: &mut impl Read) -> io::Result<Message> {
    let mut header = [0u8; 16];
    reader.read_exact(&mut header)?;

    let magic = u32::from_le_bytes(header[0..4].try_into().unwrap());
    if magic != MAGIC {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "bad magic"));
    }

    let length = u32::from_le_bytes(header[4..8].try_into().unwrap());
    let msg_type = u32::from_le_bytes(header[8..12].try_into().unwrap());
    let type_check = u32::from_le_bytes(header[12..16].try_into().unwrap());

    if type_check != !msg_type {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "bad type check"));
    }

    let mut payload = vec![0u8; length as usize];
    reader.read_exact(&mut payload)?;

    Ok(Message { msg_type, payload })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_survives_send_and_read() {
        let mut bytes = Vec::new();
        send_command(&mut bytes, 1000).unwrap();
        let message = read_message(&mut bytes.as_slice()).unwrap();

        assert_eq!(message.payload, 1000u32.to_le_bytes());
        assert_eq!(message.msg_type, msg::COMMAND);
    }

    #[test]
    fn bad_magic_is_rejected() {
        let mut bytes = Vec::new();
        send_command(&mut bytes, 1000).unwrap();
        bytes[0] = 0x00;

        assert!(read_message(&mut bytes.as_slice()).is_err());
    }

    #[test]
    fn bad_type_check_is_rejected() {
        let mut bytes = Vec::new();
        send_command(&mut bytes, 1000).unwrap();
        bytes[12] = 0x00;

        assert!(read_message(&mut bytes.as_slice()).is_err());
    }
}
