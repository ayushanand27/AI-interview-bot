/**
 * Ambient microphone monitor — sudden spikes, sustained elevated noise
 * (call-like background audio), and muted/silent mic integrity signals.
 * No speech recognition or call-app detection.
 */

export type AmbientEventType =
  | "loud_audio"
  | "sustained_noise"
  | "mic_muted"
  | "mic_silent";

export type AmbientEventHandler = (
  type: AmbientEventType,
  message: string,
) => void;

const CALIBRATION_MS = 2500;
const CHECK_INTERVAL_MS = 100;
const SPIKE_MULTIPLIER = 2.8;
const MIN_ABSOLUTE_LEVEL = 0.12;
const SPIKE_COOLDOWN_MS = 15000;

/** Sustained elevation vs quiet baseline (WhatsApp-call class signal). */
const SUSTAINED_MULTIPLIER = 1.7;
const SUSTAINED_MIN_LEVEL = 0.045;
const SUSTAINED_MS = 8000;
const SUSTAINED_SPEECH_MS = 14000;
const SUSTAINED_COOLDOWN_MS = 20000;

const MIC_CHECK_MS = 1000;
const SILENT_MS = 12000;
const MIC_EVENT_COOLDOWN_MS = 30000;

const MESSAGES: Record<AmbientEventType, string> = {
  loud_audio: "Please maintain a quiet environment",
  sustained_noise:
    "Unusual ambient audio detected — keep the room quiet and avoid other calls",
  mic_muted: "Microphone muted or disconnected — unmute to continue",
  mic_silent: "No microphone signal detected — check your mic input",
};

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
  onEvent: AmbientEventHandler,
  options?: { isSpeechActive?: () => boolean },
): () => void {
  const audioTracks = stream.getAudioTracks();
  if (audioTracks.length === 0) {
    onEvent("mic_muted", MESSAGES.mic_muted);
    return () => {};
  }

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
  let lastSpikeAt = 0;
  let lastSustainedAt = 0;
  let lastMicEventAt = 0;
  let elevatedSince: number | null = null;
  let silentSince: number | null = null;

  const fire = (type: AmbientEventType) => {
    onEvent(type, MESSAGES[type]);
  };

  const intervalId = window.setInterval(() => {
    const speechActive = Boolean(options?.isSpeechActive?.());
    const level = measureRms(analyser, buffer);

    if (!calibrated) {
      // Prefer quiet calibration samples (ignore loud speech/call during warmup).
      if (level < 0.08) {
        calibrationSamples.push(level);
      }
      if (Date.now() - calibrationStart >= CALIBRATION_MS) {
        const samples =
          calibrationSamples.length > 0 ? calibrationSamples : [0.02];
        const avg = samples.reduce((a, b) => a + b, 0) / samples.length || 0.02;
        baseline = Math.max(avg, 0.015);
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
    const spikeThreshold = Math.max(
      baseline * SPIKE_MULTIPLIER,
      MIN_ABSOLUTE_LEVEL,
    );
    const suddenSpike = level > spikeThreshold && level > recentAvg * 1.75;

    if (
      suddenSpike &&
      !speechActive &&
      Date.now() - lastSpikeAt >= SPIKE_COOLDOWN_MS
    ) {
      lastSpikeAt = Date.now();
      fire("loud_audio");
    }

    const sustainedFloor = Math.max(
      baseline * SUSTAINED_MULTIPLIER,
      SUSTAINED_MIN_LEVEL,
    );
    const needMs = speechActive ? SUSTAINED_SPEECH_MS : SUSTAINED_MS;
    if (level >= sustainedFloor) {
      if (elevatedSince == null) elevatedSince = Date.now();
      else if (
        Date.now() - elevatedSince >= needMs &&
        Date.now() - lastSustainedAt >= SUSTAINED_COOLDOWN_MS
      ) {
        lastSustainedAt = Date.now();
        elevatedSince = Date.now();
        fire("sustained_noise");
      }
    } else {
      elevatedSince = null;
    }
  }, CHECK_INTERVAL_MS);

  const micIntervalId = window.setInterval(() => {
    const tracks = stream.getAudioTracks();
    const live = tracks.filter((t) => t.readyState === "live");
    const enabled = live.some((t) => t.enabled && !t.muted);
    const now = Date.now();

    if (tracks.length === 0 || live.length === 0 || !enabled) {
      silentSince = null;
      if (now - lastMicEventAt >= MIC_EVENT_COOLDOWN_MS) {
        lastMicEventAt = now;
        fire("mic_muted");
      }
      return;
    }

    // Soft silence check using analyser when calibrated.
    if (!calibrated) return;
    const level = measureRms(analyser, buffer);
    if (level < 0.004) {
      if (silentSince == null) silentSince = now;
      else if (
        now - silentSince >= SILENT_MS &&
        now - lastMicEventAt >= MIC_EVENT_COOLDOWN_MS
      ) {
        lastMicEventAt = now;
        silentSince = now;
        fire("mic_silent");
      }
    } else {
      silentSince = null;
    }
  }, MIC_CHECK_MS);

  return () => {
    window.clearInterval(intervalId);
    window.clearInterval(micIntervalId);
    source.disconnect();
    void audioContext.close();
  };
}
