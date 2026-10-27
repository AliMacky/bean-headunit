slint::slint! {
    export component MainWindow inherits Window {
        width: 1024px;
        height: 600px;
        title: "bean-ui";
        background: #000000;

        in property <bool> water-known;
        in property <int> water-c;

        Text {
            text: root.water-known ? "WATER: " + root.water-c + "°C" : "WATER: --";
            color: #C9A26B;
            font-size: 48px;
        }
    }
}

fn main() -> Result<(), slint::PlatformError> {
    let temp: Option<i16> = Some(82);
    let window = MainWindow::new()?;

    if let Some(t) = temp {
        window.set_water_known(true);
        window.set_water_c(i32::from(t));
    } else {
        window.set_water_known(false);
    }

    window.run()
}
