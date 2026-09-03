# DRISHTI: Native Android Accessibility & Architecture Specification

## 1. Core Philosophy: Blind-First UX

DRISHTI rejects conventional screen-centric UI. The Android app acts as a low-latency, headless sensor harness designed for hands-free, zero-look operation. It translates real-time spatial intelligence from the edge backend into direct physical feedback (haptics and 3D audio).

---

## 2. Hardware Control & Screen-Off Execution

### Screen-Off Walking Mode (`ForegroundService`)

* **Perspective:** Users wear the phone in a chest harness, lanyard, or pocket with the camera facing forward. Navigation must run uninterrupted without keeping the screen active or draining battery on visual rendering.
* **Technical Implementation:**
* Wrap the `CameraX` frame engine and network loop in a persistent Android `ForegroundService`.
* Maintain a persistent low-priority system notification to prevent the Android OS memory killer from terminating the frame streaming loop.
* Keep the `ImageAnalysis.Analyzer` pipeline active even when the screen is locked or turned off.



### Hardware Button Intercepts

* **Perspective:** Visually impaired users should not search for touch targets on glass to trigger key actions while moving.
* **Technical Implementation:**
* Override Activity-level `onKeyDown` and `onKeyUp` methods:
* `KeyEvent.KEYCODE_VOLUME_UP`: Intercepts single/double clicks to trigger an on-demand snapshot for OCR or VLM scene description.
* `KeyEvent.KEYCODE_VOLUME_DOWN`: Triggers instant emergency SOS broadcast and logging.


* System volume levels are adjusted via software sliders inside app settings to avoid conflict with physical button inputs.



---

## 3. Spatial Audio Engine

### 3D Spatial Audio "Sonar" (Audio Compass)

* **Perspective:** Hearing *"Obstacle on the left"* as spoken text creates cognitive fatigue. Users should intuitively *feel* where an object is located in physical space through sound directionality and tone.
* **Technical Implementation:**
* Map YOLO bounding box X-coordinates directly to stereo audio channels using `AudioTrack.setStereoVolume(leftVolume, rightVolume)` or the Android `Spatializer` API:
* $X = -1.0$ (Far Left): `leftVolume = 1.0`, `rightVolume = 0.0`
* $X = 0.0$ (Center): `leftVolume = 1.0`, `rightVolume = 1.0`
* $X = 1.0$ (Far Right): `leftVolume = 0.0`, `rightVolume = 1.0`


* Map bounding box area (proximity indicator) to pitch/frequency. As a hazard approaches, the tone pitch increases linearly, providing instantaneous spatial feedback without text-to-speech processing delays.



### Smart Audio Routing & TalkBack Coexistence

* **Perspective:** Voice navigation alerts must not clash with native TalkBack screen readers, phone calls, or background media. Critical safety alerts must override all other audio streams instantly.
* **Technical Implementation:**
* Initialize native `TextToSpeech` (TTS) using `AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY`.
* Manage focus via `AudioManager.requestAudioFocus()`.
* Apply **Audio Ducking**: Automatically lower background media or TalkBack volume when DRISHTI issues spatial warnings.
* Use `TextToSpeech.QUEUE_FLUSH` for `CRITICAL` risk states (e.g., open manhole, approaching vehicle) to abort ongoing speech and output immediate safety commands (e.g., *"STOP"*).



---

## 4. Haptic Perception Engine

### Waveform Language (`VibratorManager`)

* **Perspective:** In noisy urban traffic where spatial audio can be drowned out, directional vibrations deliver an alternate, non-auditory channel for hazard perception.
* **Technical Implementation:**
* Use Android `VibratorManager` with `VibrationEffect.createWaveform(timings, amplitudes, repeat)`.
* **Haptic Dictionary:**
* `CRITICAL_STOP`: High-amplitude, 50 ms alternating pulse pattern.
* `CORRIDOR_CLEAR`: Smooth, low-amplitude continuous pulse.
* `MOVE_LEFT`: Asymmetric left-leaning double pulse.
* `MOVE_RIGHT`: Asymmetric right-leaning double pulse.


* Invoke `Vibrator.cancel()` before firing new effects to prevent queue delay build-up during real-time movement.



### The "Phantom Cane" (Gyroscopic Haptic Radar)

* **Perspective:** Digitizes the traditional white-cane sweeping motion. The user sweeps the phone across a room, feeling physical resistance (vibrations) when pointing at hazards.
* **Technical Implementation:**
* Register a `SensorEventListener` for `Sensor.TYPE_GYROSCOPE` and `Sensor.TYPE_ACCELEROMETER`.
* Synchronize camera frame bounding boxes with current orientation angles.
* Dynamically adjust vibration pulse frequencies based on object proximity along the current camera center axis:
* **3.0 Meters:** Slow 1-second pulse delay.
* **1.0 Meter:** Rapid 200 ms pulse delay.
* **0.3 Meters:** Solid continuous buzz.





---

## 5. Zero-Look Touch Interaction & Accessibility UI

### Full-Screen Touch Targets

* **Perspective:** Eliminates precision button targeting. The entire screen functions as a single gesture target.
* **Technical Implementation:**
* Implement a custom `GestureDetector.SimpleOnGestureListener`:
* **Double-Tap Anywhere:** Toggle Walk Loop Start/Stop.
* **Two-Finger Swipe Right:** Trigger OCR / Explore Mode.
* **Long Press (2 Seconds):** Trigger VLM Snapshot mode.
* **Triple-Tap:** Cancel current alert / Reset navigation state.





### High-Contrast Low-Vision Support

* **Perspective:** Users with partial light perception or low vision need clean, glare-free visual cues without small text or complex layouts.
* **Technical Implementation:**
* Solid `#000000` pitch-black background to minimize screen glare and conserve OLED battery.
* Massive typography in high-contrast yellow (`#FFFF00`) or safety red (`#FF0000`) for system states (`WALKING`, `STOP`, `PAUSED`).
* Explicit `contentDescription` attributes attached to all UI elements for native TalkBack compliance.



---

## 6. On-Demand Contextual Snapshot Loop (VLM & OCR)

* **Perspective:** Continuous scene description via large models is too slow for active walking, but essential when standing still to read signs, identify room numbers, or check bus route banners.
* **Technical Implementation:**
* **Walk Mode (Continuous):** Real-time YOLO11n + SegFormer inference runs at 15+ FPS over local WebSocket/HTTP streams.
* **Snapshot Trigger (On-Demand):** Triggered via Volume Up click or screen long-press.
* **Processing:**
1. Pauses continuous frame streaming temporarily.
2. Captures a single uncompressed high-resolution frame via `ImageCapture`.
3. Sends payload to backend `POST /api/v1/explore` (Tesseract 5 OCR) or `POST /api/v1/vlm/query` (Local Moondream2 / Qwen2-VL).
4. Speaks the returned scene analysis via TTS ducked audio.
5. Automatically resumes the real-time Walk Loop.





---

## 7. Kotlin Architecture & Tech Stack Summary

| Subsystem | Android API / Library | Function |
| --- | --- | --- |
| **Camera Feed** | `androidx.camera.core.ImageAnalysis` | YUV_420_888 frame extraction for edge backend |
| **Background Execution** | `android.app.ForegroundService` | Screen-off execution and memory persistence |
| **Hardware Intercepts** | `Activity.onKeyDown` | Physical Volume button gesture bindings |
| **Haptics** | `android.os.VibratorManager` | Custom waveform vibration feedback |
| **Sensors** | `android.hardware.SensorManager` | Gyroscope fusion for "Phantom Cane" radar |
| **Audio Pan/Pitch** | `android.media.AudioTrack` / `Spatializer` | 3D stereo spatial positioning |
| **Voice Output** | `android.speech.tts.TextToSpeech` | Audio-ducked spoken feedback |
| **Touch UI** | `android.view.GestureDetector` | Screen-wide zero-look gesture recognition |