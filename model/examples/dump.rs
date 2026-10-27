use std::io;
use std::os::unix::net::UnixStream;

use bean_model::{SOCKET_PATH, read_frame};

fn main() -> io::Result<()> {
    let mut socket = UnixStream::connect(SOCKET_PATH)?;
    println!("connected to {SOCKET_PATH}");

    loop {
        let state = read_frame(&mut socket)?;
        println!("{state:?}");
    }
}
