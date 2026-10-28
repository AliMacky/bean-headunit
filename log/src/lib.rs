use log::{LevelFilter, Log, Metadata, Record};
use std::time::Instant;

struct Logger {
    start: Instant,
}

fn format_line(secs: f64, record: &Record) -> String {
    format!(
        "[{:8.3}] {:<5} {}: {}",
        secs,
        record.level(),
        record.target(),
        record.args()
    )
}

impl Log for Logger {
    fn enabled(&self, metadata: &Metadata) -> bool {
        metadata.level() <= LevelFilter::Info
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        eprintln!(
            "{}",
            format_line(self.start.elapsed().as_secs_f64(), record)
        );
    }

    fn flush(&self) {}
}

pub fn init() -> Result<(), log::SetLoggerError> {
    let logger = Logger {
        start: Instant::now(),
    };
    log::set_boxed_logger(Box::new(logger))?;
    log::set_max_level(LevelFilter::Info);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use log::Level;

    #[test]
    fn info_and_above_are_enalbled() {
        let logger = Logger {
            start: Instant::now(),
        };
        assert!(logger.enabled(&Metadata::builder().level(Level::Warn).build()));
        assert!(logger.enabled(&Metadata::builder().level(Level::Info).build()));
    }

    #[test]
    fn debug_is_filtered_out() {
        let logger = Logger {
            start: Instant::now(),
        };
        assert!(!logger.enabled(&Metadata::builder().level(Level::Debug).build()));
        assert!(!logger.enabled(&Metadata::builder().level(Level::Trace).build()));
    }

    #[test]
    fn line_format() {
        assert_eq!(
            format_line(
                12.00,
                &Record::builder()
                    .level(Level::Warn)
                    .target("bean_ui")
                    .args(format_args!("hi"))
                    .build()
            ),
            "[  12.000] WARN  bean_ui: hi"
        );
    }
}
