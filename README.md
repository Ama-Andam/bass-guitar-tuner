# WaveNode

<!-- TODO (Emmanuela): write a short intro in your own voice here.
     A couple of sentences on what WaveNode is and why you built it.
     Everything below is drafted for you to edit, cut, or rework. -->

WaveNode is a custom Arduino-compatible development board with an onboard
microphone front-end: an ATmega328P plus a mic preamp, biasing, and
anti-alias filtering wired into the ADC. It is meant to be reused across audio
projects. The first thing built on it is a real-time tuner for 5-string bass.

![System block diagram](docs/block-diagram.svg)

## The board and the demo

- **WaveNode (the board):** a reusable Arduino-compatible platform that captures
  and conditions an audio signal in hardware, so any project built on it starts
  with a clean signal into the ADC.
- **Bass tuner (the demo):** firmware + a host app that turn that signal into a
  live note readout. Pluck a string and a browser shows the note, cents sharp or
  flat, and lights up the matching string (B0, E1, A1, D2, G2).

## Signal chain

![Signal chain](docs/signal-chain.svg)

The analog capture and conditioning happen on the WaveNode board. Detection and
display run on a host (a Jetson Nano during development):

1. **Capture (WaveNode).** The mic feeds a preamp and bias/filter stage, then the
   ATmega328P samples it at a fixed 2 kHz and streams each 10-bit reading to the
   host as 2 raw bytes over USB serial at 115200 baud.
2. **Detection (host, Python).** The host reassembles the samples, removes the DC
   offset, and runs autocorrelation to find the pitch period. A median filter
   smooths the reading; the result converts to the nearest note and cents.
3. **Display (Flask web app).** A Flask server exposes the current note at
   `/pitch`; a single-page frontend polls it and drives the note readout, the
   cents needle, and the string ring, served on the local network.

## Running the tuner

On the host, with the board plugged in over USB:

```bash
pip3 install -r requirements.txt
python3 app.py
```

Then open `http://<host-ip>:5000` in a browser on the same network. The firmware
is in `firmware/`; flash it with the Arduino IDE. `SERIAL_PORT` in `app.py`
defaults to `/dev/ttyACM0`.

## Project layout

```
README.md                      this file
docs/                          block diagrams, screenshots, board photos
hardware/
  schematic/                   WaveNode schematic (Altium + PDF)
  pcb/                         layout, 3D render, gerbers
  bom/                         bill of materials
firmware/bass_tuner_nano.ino   samples the mic, streams over serial
app.py                         host backend: serial read, detection, API
index.html                     tuner frontend
requirements.txt               Python dependencies
```

## Project status

- [x] Working breadboard prototype (mic, Arduino, host) with live tuning
- [x] Pitch detection, note/cents readout, web UI
- [x] System and signal-chain block diagrams
- [ ] WaveNode schematic (circuit design)
- [ ] PCB layout
- [ ] Fabrication via JLCPCB and bring-up

## Design notes

Real findings from the prototype, kept honestly:

- **Microphone sensitivity.** A bare electret into the ADC gave a weak signal for
  quiet low bass. WaveNode addresses this directly by designing a proper preamp
  and bias/filter front-end onto the board rather than relying on a raw mic.
- **Sample rate vs. low-end resolution.** At 2 kHz, lag steps are coarse at the
  lowest notes; parabolic interpolation helps refine the estimate.
- **Subharmonic detection.** The high string can occasionally lock onto a lower
  octave; stronger subharmonic rejection is the fix.
