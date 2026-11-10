# OpenNB4-CFW

Replacement firmware for the Flysky Noble NB4 radio.

Early development. There is no release yet.

## Install

Coming with the first release. The firmware will be installed over the radio's
USB connection with a single installer program.

## Uninstall

Coming with the first release. Uninstalling will restore the vendor firmware.

## Build from source

    git clone https://github.com/Muwusiz/OpenNB4-CFW.git
    cd OpenNB4-CFW
    python firmware/build.py --profile stable --release 1

The image is written to `dist/`. Requires Python 3.
