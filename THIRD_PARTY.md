# Third-party components

This repository contains the transfer tool and its own compatibility patches. Game files, Microsoft fonts, host keys and credentials are not distributed.

| Component | Version / source | License |
| --- | --- | --- |
| Box64 | 0.4.5, fbba162, [source](https://github.com/ptitSeb/box64/tree/fbba162), [Debian build packaging](https://github.com/Pi-Apps-Coders/box64-debs) | MIT |
| Wine | 10.0 amd64 WoW64, [build](https://github.com/Kron4ek/Wine-Builds/releases/tag/10.0), [source](https://gitlab.winehq.org/wine/wine/-/tree/wine-10.0), [build scripts](https://github.com/Kron4ek/Wine-Builds) | LGPL-2.1-or-later and individual files |
| libADLMIDI | [1.5.1 source](https://github.com/Wohlstand/libADLMIDI/releases/tag/v1.5.1), DOSBox OPL3 emulator | LGPL-3.0-or-later; embedded components/banks have their own notices |
| Xvfb, X11 libraries, xkb-data | Debian 12 bookworm packages | MIT/X11 and individual files |
| ALSA lib | Debian 12 bookworm | LGPL-2.1-or-later |
| libgcc_s | Debian 12 GCC 12 cross runtime | GPL-3.0 with GCC Runtime Library Exception |
| TimGM6mb | Debian `timgm6mb-soundfont` 1.3-5 | GPL-2.0 |
| Paramiko | 3.5.1 | LGPL-2.1 |
| CPython / Tcl / Tk | build environment | PSF / Tcl/Tk licenses |
| PyInstaller bootloader | 6.16.0 | GPL with bootloader exception |
| cryptography, cffi, bcrypt, PyNaCl | resolved Python build dependencies | Their upstream licenses |

The runtime archive includes upstream libADLMIDI source and license texts, Debian copyright files and package versions under `licenses/`. `runtime/dependencies.json` pins externally downloaded archives by SHA-256. Native helper sources and build scripts are in this repository.

When distributing compiled third-party components, retain these notices and provide the corresponding source and build information required by their licenses. A local build is a release candidate, not an automatic GitHub release. Microsoft `msgothic.ttc` is read from the executing user's Windows installation and transferred separately to that user's device.
