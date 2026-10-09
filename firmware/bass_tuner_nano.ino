// Bass Tuner - Arduino Nano firmware
//
// Samples the microphone on A0 at a fixed 2 kHz using a hardware timer,
// and streams each 10-bit reading to the host as 2 raw bytes (little-endian)
// over USB serial at 115200 baud. The host (a Jetson Nano running app.py)
// reassembles the samples and runs the pitch detection.

const int micAnalogPin = A0;
const int sampleRateHz = 2000;

volatile bool sampleReady = false;

void setup() {
  Serial.begin(115200);
  analogRead(micAnalogPin);       // prime the ADC

  // Timer1 in CTC mode: fire a compare interrupt at the sample rate
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1  = 0;
  OCR1A  = (16000000UL / 8 / sampleRateHz) - 1;   // = 999 at 2 kHz
  TCCR1B |= (1 << WGM12);         // CTC mode
  TCCR1B |= (1 << CS11);          // prescaler 8
  TIMSK1 |= (1 << OCIE1A);        // enable compare-match interrupt
  interrupts();
}

ISR(TIMER1_COMPA_vect) {
  sampleReady = true;
}

void loop() {
  if (sampleReady) {
    sampleReady = false;
    uint16_t micReading = analogRead(micAnalogPin);      // 0..1023
    Serial.write((uint8_t)(micReading & 0xFF));          // low byte
    Serial.write((uint8_t)(micReading >> 8));            // high byte
  }
}
