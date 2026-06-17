/**
 * Ambient microphone level monitor — detects sudden loud sounds (e.g. talking to someone).
 * No speech recognition; RMS threshold only.
 */

const CALIBRATION_MS = 2500;
const CHECK_INTERVAL_MS = 100;
const SPIKE_MULTIPLIER = 2.8;
const MIN_ABSOLUTE_LEVEL = 0.12;
const COOLDOWN_MS = 15000;

function measureRms(analyser: AnalyserNode, buffer: Uint8Array): number {
  analyser.getByteTimeDomainData(buffer);
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) {
    const sample = (buffer[i] - 128) / 128;
    sum += sample * sample;
  }
  return Math.sqrt(sum / buffer.length);
}

export function startAmbientAudioMonitor(
  stream: MediaStream,
  onLoudAudio: () => void,
): () => void {
  const audioContext = new AudioContext();
  const source = audioContext.createMediaStreamSource(stream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);

  const buffer = new Uint8Array(analyser.fftSize);
  const calibrationSamples: number[] = [];
  const calibrationStart = Date.now();
  let baseline = 0.02;
  let calibrated = false;
  const recentLevels: number[] = [];
  let lastTriggerAt = 0;

  const intervalId = window.setInterval(() => {
    const level = measureRms(analyser, buffer);

    if (!calibrated) {
      calibrationSamples.push(level);
      if (Date.now() - calibrationStart >= CALIBRATION_MS) {
        const avg =
          calibrationSamples.reduce((a, b) => a + b, 0) /
            calibrationSamples.length || 0.02;
        baseline = Math.max(avg, 0.02);
        calibrated = true;
      }
      return;
    }

    recentLevels.push(level);
    if (recentLevels.length > 25) {
      recentLevels.shift();
    }

    const recentAvg =
      recentLevels.reduce((a, b) => a + b, 0) / recentLevels.length;
    const threshold = Math.max(baseline * SPIKE_MULTIPLIER, MIN_ABSOLUTE_LEVEL);
    const suddenSpike = level > threshold && level > recentAvg * 1.75;

    if (suddenSpike && Date.now() - lastTriggerAt >= COOLDOWN_MS) {
      lastTriggerAt = Date.now();
      onLoudAudio();
    }
  }, CHECK_INTERVAL_MS);

  return () => {
    window.clearInterval(intervalId);
    source.disconnect();
    void audioContext.close();
  };
}
