use serde::{Deserialize, Serialize};

pub const PROTOCOL_VERSION: u16 = 1;

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
}
