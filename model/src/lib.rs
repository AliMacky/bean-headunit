use serde::{Deserialize, Serialize};
use std::io::{self, Read, Write};

pub const SOCKET_PATH: &str = "/tmp/bean.sock";
pub const PROTOCOL_VERSION: u16 = 1;
pub const MAX_FRAME: usize = 64 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Theme {
    Night,
    Day,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ObdStatus {
    NoAdapter,
    Connecting,
    NoResponse,
    Connected,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CarState {
    pub water_temp_c: Option<i16>,
    pub rpm: Option<u16>,
    pub battery_v: Option<f32>,
    pub obd_status: ObdStatus,
    pub theme: Theme,
}

pub fn encode(state: &CarState) -> Result<Vec<u8>, rmp_serde::encode::Error> {
    rmp_serde::to_vec_named(state)
}

pub fn decode(bytes: &[u8]) -> Result<CarState, rmp_serde::decode::Error> {
    rmp_serde::from_slice(bytes)
}

pub fn write_frame(w: &mut impl Write, state: &CarState) -> io::Result<()> {
    let bytes = encode(state).map_err(io::Error::other)?;
    if bytes.len() > MAX_FRAME {
        return Err(io::Error::other("Frame exceeds MAX_FRAME length"));
    }

    let len = bytes.len() as u32;
    w.write_all(&len.to_be_bytes())?;
    w.write_all(&bytes)?;
    Ok(())
}

pub fn read_frame(r: &mut impl Read) -> io::Result<CarState> {
    let mut len_buf = [0u8; 4];
    r.read_exact(&mut len_buf)?;

    let len = u32::from_be_bytes(len_buf) as usize;
    if len > MAX_FRAME {
        return Err(io::Error::other("Frame exceeds MAX_FRAME length"));
    }

    let mut msg_buf = vec![0u8; len];
    r.read_exact(&mut msg_buf)?;
    decode(&msg_buf).map_err(io::Error::other)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip() {
        let original = CarState {
            water_temp_c: Some(92),
            rpm: None,
            battery_v: Some(12.33),
            obd_status: ObdStatus::NoAdapter,
            theme: Theme::Night,
        };

        let encoded = encode(&original).unwrap();
        let decoded = decode(&encoded).unwrap();

        assert_eq!(original, decoded)
    }

    #[test]
    fn two_frames_in_a_row() {
        let first = CarState {
            water_temp_c: Some(92),
            rpm: None,
            battery_v: Some(12.33),
            obd_status: ObdStatus::NoAdapter,
            theme: Theme::Night,
        };
        let second = CarState {
            water_temp_c: None,
            rpm: Some(1200),
            battery_v: Some(9.00),
            obd_status: ObdStatus::Connected,
            theme: Theme::Day,
        };

        let mut buf: Vec<u8> = Vec::new();
        write_frame(&mut buf, &first).unwrap();
        write_frame(&mut buf, &second).unwrap();

        let mut reader = &buf[..];
        let first_got = read_frame(&mut reader).unwrap();
        let second_got = read_frame(&mut reader).unwrap();

        assert_eq!(first, first_got);
        assert_eq!(second, second_got);
    }

    #[test]
    fn rejects_huge_length() {
        let bad = [0xFF, 0xFF, 0xFF, 0xFF];
        let mut reader = &bad[..];

        let err = read_frame(&mut reader).unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::Other);
    }
}
