"""
Bass Tuner web app - backend.

Reads the Arduino mic stream over serial, runs autocorrelation pitch
detection, and serves the current note over HTTP. The frontend (index.html)
polls /pitch and draws the tuner.

Run on the Jetson:
    python3 app.py
Then open http://<jetson-ip>:5000 in any browser on the network.
"""

import threading
import time

import numpy as np
import serial
from flask import Flask, jsonify, send_from_directory

# ---- config ----
SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200
SAMPLE_RATE_HZ = 2000
CHUNK_SIZE = 700          # smaller chunk = faster updates
HISTORY_LENGTH = 5
SWING_THRESHOLD = 8       # lower = holds a fading note longer
STRENGTH_THRESHOLD = 0.4  # lower = more forgiving on weak signal
HOLD_SECONDS = 1.5        # keep showing the last note this long after signal drops

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F",
              "F#", "G", "G#", "A", "A#", "B"]

# 5-string bass open strings (low to high)
BASS_STRINGS = [
    {"name": "B0", "freq": 30.87},
    {"name": "E1", "freq": 41.20},
    {"name": "A1", "freq": 55.00},
    {"name": "D2", "freq": 73.42},
    {"name": "G2", "freq": 98.00},
]

# ---- shared state (written by the reader thread, read by Flask) ----
state = {
    "note": None,
    "octave": None,
    "freq": 0.0,
    "cents": 0.0,
    "direction": "listening",
    "active": False,
}
state_lock = threading.Lock()


def freq_to_note(freq):
    if freq <= 0:
        return None
    midi = 69 + 12 * np.log2(freq / 440.0)
    nearest = int(round(midi))
    name = NOTE_NAMES[nearest % 12]
    octave = nearest // 12 - 1
    exact = 440.0 * (2 ** ((nearest - 69) / 12))
    cents = 1200 * np.log2(freq / exact)
    return name, octave, cents


def detect_pitch(samples, sample_rate, min_hz=25, max_hz=400):
    samples = samples - np.mean(samples)
    corr = np.correlate(samples, samples, mode="full")
    corr = corr[len(corr) // 2:]
    if corr[0] == 0:
        return 0.0, 0.0
    norm = corr / corr[0]

    min_lag = int(sample_rate / max_hz)
    max_lag = min(int(sample_rate / min_hz), len(corr) - 1)
    region = norm[min_lag:max_lag]
    if len(region) == 0:
        return 0.0, 0.0

    tallest = np.max(region)
    threshold = 0.85 * tallest
    peak_lag = min_lag + int(np.argmax(region))
    for lag in range(min_lag + 1, max_lag - 1):
        if norm[lag] > threshold and norm[lag] > norm[lag - 1] and norm[lag] > norm[lag + 1]:
            peak_lag = lag
            break

    strength = norm[peak_lag]

    # parabolic interpolation for a finer peak position
    if 0 < peak_lag < len(norm) - 1:
        y0, y1, y2 = norm[peak_lag - 1], norm[peak_lag], norm[peak_lag + 1]
        denom = y0 - 2 * y1 + y2
        if denom != 0:
            peak_lag = peak_lag + 0.5 * (y0 - y2) / denom

    freq = sample_rate / peak_lag
    return freq, strength


def reader_loop():
    """Runs forever in a background thread, updating `state`."""
    while True:
        try:
            conn = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        except Exception as e:
            print(f"could not open {SERIAL_PORT}: {e}. retrying in 2s")
            with state_lock:
                state["direction"] = "no device"
                state["active"] = False
            time.sleep(2)
            continue

        byte_buffer = bytearray()
        sample_buffer = []
        history = []
        last_good_time = 0.0
        print("serial connected, reading...")

        try:
            while True:
                byte_buffer += conn.read(256)
                while len(byte_buffer) >= 2:
                    lo = byte_buffer[0]
                    hi = byte_buffer[1]
                    del byte_buffer[:2]
                    sample_buffer.append(lo | (hi << 8))

                if len(sample_buffer) >= CHUNK_SIZE:
                    block = np.array(sample_buffer[:CHUNK_SIZE])
                    sample_buffer = sample_buffer[CHUNK_SIZE:]

                    swing = int(block.max() - block.min())
                    freq, strength = detect_pitch(block, SAMPLE_RATE_HZ)

                    if swing > SWING_THRESHOLD and strength > STRENGTH_THRESHOLD:
                        history.append(freq)
                        if len(history) > HISTORY_LENGTH:
                            history.pop(0)
                        smooth = float(np.median(history))
                        result = freq_to_note(smooth)
                        if result:
                            name, octave, cents = result
                            direction = ("in tune" if abs(cents) < 5
                                         else ("sharp" if cents > 0 else "flat"))
                            with state_lock:
                                state.update({
                                    "note": name,
                                    "octave": octave,
                                    "freq": round(smooth, 1),
                                    "cents": round(cents, 1),
                                    "direction": direction,
                                    "active": True,
                                })
                            last_good_time = time.time()
                    else:
                        history = []
                        # hold the last note for a moment so brief dropouts
                        # (a decaying pluck) don't make the display flicker
                        if time.time() - last_good_time > HOLD_SECONDS:
                            with state_lock:
                                state["direction"] = "listening"
                                state["active"] = False
        except Exception as e:
            print(f"serial read error: {e}. reconnecting")
            try:
                conn.close()
            except Exception:
                pass
            time.sleep(1)


# ---- web server ----
app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/pitch")
def pitch():
    with state_lock:
        return jsonify(dict(state))


@app.route("/strings")
def strings():
    return jsonify(BASS_STRINGS)


if __name__ == "__main__":
    t = threading.Thread(target=reader_loop, daemon=True)
    t.start()
    # host 0.0.0.0 so other devices on the network can reach it
    app.run(host="0.0.0.0", port=5000, threaded=True)
