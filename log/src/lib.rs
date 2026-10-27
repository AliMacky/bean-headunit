use log::{LevelFilter, Log, Metadata, Record};
use std::time::Instant;

struct Logger {
    start: Instant,
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
            "[{:8.3}] {:<5} {}: {}",
            self.start.elapsed().as_secs_f64(),
            record.level(),
            record.target(),
            record.args()
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
