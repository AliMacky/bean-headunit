//! Turns the dongle's H.264 into RGB frames. Knows nothing about the UI.

use ffmpeg::codec;
use ffmpeg::format::Pixel;
use ffmpeg::software::scaling::{Context as Scaler, Flags};
use ffmpeg::util::frame::Video as VideoFrame;
use ffmpeg_next as ffmpeg;

/// The first 20 bytes of a video message are a header, the rest is H.264.
const HEADER_LEN: usize = 20;

pub struct RgbFrame<'a> {
    pub width: u32,
    pub height: u32,
    /// Bytes per row in `data`, which can be more than `width * 3`.
    pub stride: usize,
    pub data: &'a [u8],
}

pub struct VideoDecoder {
    decoder: ffmpeg::decoder::Video,
    scaler: Option<Scaler>,
    yuv: VideoFrame,
    rgb: VideoFrame,
}

impl VideoDecoder {
    pub fn new() -> Result<VideoDecoder, ffmpeg::Error> {
        ffmpeg::init()?;
        let h264 = ffmpeg::decoder::find(codec::Id::H264).ok_or(ffmpeg::Error::DecoderNotFound)?;
        let decoder = codec::Context::new_with_codec(h264).decoder().video()?;

        Ok(VideoDecoder {
            decoder,
            scaler: None,
            yuv: VideoFrame::empty(),
            rgb: VideoFrame::empty(),
        })
    }

    /// Decodes one video message payload and calls `on_frame` for each finished frame.
    pub fn decode(
        &mut self,
        payload: &[u8],
        mut on_frame: impl FnMut(RgbFrame),
    ) -> Result<(), ffmpeg::Error> {
        let h264 = payload.get(HEADER_LEN..).unwrap_or_default();
        self.decoder.send_packet(&ffmpeg::Packet::copy(h264))?;

        while self.decoder.receive_frame(&mut self.yuv).is_ok() {
            let (format, width, height) = (self.yuv.format(), self.yuv.width(), self.yuv.height());

            // The scaler is built for one format and size, so remake it if those change.
            let stale = self.scaler.as_ref().is_none_or(|s| {
                let input = s.input();
                input.format != format || input.width != width || input.height != height
            });
            if stale {
                self.scaler = Some(Scaler::get(
                    format,
                    width,
                    height,
                    Pixel::RGB24,
                    width,
                    height,
                    Flags::FAST_BILINEAR,
                )?);
            }

            if let Some(scaler) = self.scaler.as_mut() {
                scaler.run(&self.yuv, &mut self.rgb)?;
                on_frame(RgbFrame {
                    width,
                    height,
                    stride: self.rgb.stride(0),
                    data: self.rgb.data(0),
                });
            }
        }
        Ok(())
    }
}
