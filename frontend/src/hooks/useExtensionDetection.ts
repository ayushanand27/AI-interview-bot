// frontend/src/hooks/useExtensionDetection.ts

const KNOWN_RECORDING_EXTENSIONS: Record<string, string> = {
  liecbddmkiiihnedobmlmillhodjkdmb: "Loom",
  mmeijimgabbpbgpdklnllpncmdofkcpn: "Screencastify",
  bpconcjcammlapcogcnnelfmaeghhagj: "Nimbus Screenshot",
  hdiaamehgchmceplikhcgggiilllnhbl: "Nimbus Screenshot & Screen Video Recorder",
  kgbfjjfmaehgdmjkmkjpgellbdggnkhl: "Screen Recorder",
  jkpbjbdagkmhpibjgafbckclnkaaapca: "Awesome Screenshot",
};

const SUSPICIOUS_CAMERA_KEYWORDS = [
  "virtual",
  "obs",
  "snap",
  "screen",
  "capture",
  "manycam",
  "droidcam",
  "epoccam",
  "camo",
  "xsplit",
];

const SCREEN_CAPTURE_LABEL_RE =
  /screen|display|monitor|window|capture|desktop/i;

export type VirtualCameraConfidence = "none" | "low" | "high";

export interface DetectedExtension {
  id: string;
  name: string;
}

export interface ExtensionScanResult {
  detected: DetectedExtension[];
  /** True when automatic Chromium extension scan ran. */
  scanSupported: boolean;
}

export interface VirtualCameraResult {
  detected: boolean;
  confidence: VirtualCameraConfidence;
  /** High confidence — block starting the interview. */
  blockRecommended: boolean;
  /** Low confidence — warn but allow with proctoring flag. */
  warnOnly: boolean;
  deviceLabels: string[];
  message: string | null;
}

export interface EnvironmentScanResult {
  extensions: ExtensionScanResult;
  virtualCamera: VirtualCameraResult;
  screenSharingActive: boolean;
  /** Screen-capture device present (soft warning only). */
  screenSharingCapability: boolean;
}

type ChromeManagementExtension = {
  id: string;
  name?: string;
  enabled?: boolean;
};

type MediaTrackSettingsEx = MediaTrackSettings & {
  displaySurface?: string;
};

function mergeExtensions(
  ...lists: DetectedExtension[][]
): DetectedExtension[] {
  const byId = new Map<string, DetectedExtension>();
  for (const list of lists) {
    for (const ext of list) {
      if (!byId.has(ext.id)) {
        byId.set(ext.id, ext);
      }
    }
  }
  return Array.from(byId.values());
}

function labelLooksSuspicious(label: string): boolean {
  const lower = label.toLowerCase();
  return SUSPICIOUS_CAMERA_KEYWORDS.some((kw) => lower.includes(kw));
}

function settingsLookVirtual(settings: MediaTrackSettingsEx | undefined): boolean {
  if (!settings) return false;
  const { width, height, frameRate } = settings;
  if (settings.displaySurface) return true;
  const commonVirtualPairs: Array<[number, number]> = [
    [640, 480],
    [1280, 720],
    [1920, 1080],
  ];
  if (
    width &&
    height &&
    commonVirtualPairs.some(([w, h]) => width === w && height === h) &&
    (frameRate === undefined || frameRate <= 15)
  ) {
    return true;
  }
  return false;
}

function scoreVirtualCameraSignal(
  label: string | undefined,
  settings: MediaTrackSettingsEx | undefined,
  hasPermission: boolean,
): number {
  let score = 0;
  const trimmed = label?.trim() ?? "";

  if (trimmed && labelLooksSuspicious(trimmed)) {
    score += 60;
  }
  if (settings?.displaySurface) {
    score += 100;
  }
  if (hasPermission && !trimmed) {
    score += 45;
  }
  if (settingsLookVirtual(settings)) {
    score += 35;
  }
  if (trimmed && SCREEN_CAPTURE_LABEL_RE.test(trimmed)) {
    score += 55;
  }
  return score;
}

function buildVirtualCameraResult(
  labels: string[],
  maxScore: number,
): VirtualCameraResult {
  const confidence: VirtualCameraConfidence =
    maxScore >= 50 ? "high" : maxScore > 0 ? "low" : "none";
  const detected = confidence !== "none";
  const blockRecommended = confidence === "high";
  const warnOnly = confidence === "low";

  let message: string | null = null;
  if (blockRecommended) {
    message = "Virtual camera detected — please use your real webcam";
  } else if (warnOnly) {
    message =
      "Your camera setup looks unusual — if you are using a virtual camera, switch to your real webcam";
  }

  return {
    detected,
    confidence,
    blockRecommended,
    warnOnly,
    deviceLabels: labels,
    message,
  };
}

function detectPassiveRecordingExtensions(): DetectedExtension[] {
  if (typeof document === "undefined") return [];

  const found: DetectedExtension[] = [];
  const win = window as unknown as Record<string, unknown>;

  const passiveChecks: Array<{
    id: string;
    name: string;
    selector?: string;
    globalKeys?: string[];
  }> = [
    {
      id: "loom-passive",
      name: "Loom",
      selector: '[id*="loom"], [class*="loom"], iframe[src*="loom"]',
      globalKeys: ["__loom", "loom"],
    },
    {
      id: "screencastify-passive",
      name: "Screencastify",
      selector: '[class*="screencastify"], [id*="screencastify"]',
      globalKeys: ["__screencastify", "screencastify"],
    },
    {
      id: "nimbus-passive",
      name: "Nimbus",
      selector: '[class*="nimbus"], [id*="nimbus"]',
    },
    {
      id: "obs-passive",
      name: "OBS",
      globalKeys: ["obsstudio"],
    },
  ];

  for (const check of passiveChecks) {
    if (check.globalKeys?.some((key) => key in win && win[key] != null)) {
      found.push({ id: check.id, name: check.name });
      continue;
    }
    if (check.selector && document.querySelector(check.selector)) {
      found.push({ id: check.id, name: check.name });
    }
  }

  if (
    navigator.webdriver ||
    Object.getOwnPropertyDescriptor(navigator, "webdriver")?.get
  ) {
    // Automation only — not an extension signal
  }

  const html = document.documentElement;
  for (const attr of ["data-screencastify", "data-loom", "data-nimbus"]) {
    if (html.hasAttribute(attr)) {
      found.push({ id: `${attr}-attr`, name: "Screen recording extension" });
    }
  }

  return found;
}

async function detectExtensionsViaConnect(): Promise<DetectedExtension[]> {
  const detected: DetectedExtension[] = [];

  if (
    typeof window === "undefined" ||
    !(window as Window & { chrome?: { runtime?: unknown } }).chrome?.runtime
  ) {
    return detected;
  }

  const runtime = (
    window as unknown as {
      chrome: { runtime: { connect: (id: string) => { disconnect: () => void } } };
    }
  ).chrome.runtime;

  for (const [id, name] of Object.entries(KNOWN_RECORDING_EXTENSIONS)) {
    try {
      const port = runtime.connect(id);
      if (port) {
        detected.push({ id, name });
        port.disconnect();
      }
    } catch {
      // Not installed or blocks connections — safe
    }
  }

  return detected;
}

async function detectExtensionsViaManagement(): Promise<DetectedExtension[]> {
  const chromeApi = (
    window as Window & {
      chrome?: {
        management?: {
          getAll: (cb: (items: ChromeManagementExtension[]) => void) => void;
        };
      };
    }
  ).chrome;

  if (!chromeApi?.management?.getAll) {
    return [];
  }

  return new Promise((resolve) => {
    try {
      chromeApi.management!.getAll((items) => {
        const found: DetectedExtension[] = [];
        for (const ext of items ?? []) {
          if (ext.enabled === false) continue;
          const name = ext.name ?? "";
          const lower = name.toLowerCase();
          if (
            lower.includes("record") ||
            lower.includes("screen") ||
            lower.includes("loom") ||
            lower.includes("nimbus")
          ) {
            found.push({ id: ext.id, name: name || ext.id });
          }
        }
        resolve(found);
      });
    } catch {
      resolve([]);
    }
  });
}

export async function detectScreenRecordingExtensions(): Promise<ExtensionScanResult> {
  const viaConnect = await detectExtensionsViaConnect();
  const viaManagement = await detectExtensionsViaManagement();
  const viaPassive = detectPassiveRecordingExtensions();
  const detected = mergeExtensions(viaConnect, viaManagement, viaPassive);

  const scanSupported =
    typeof window !== "undefined" &&
    Boolean(
      (window as Window & { chrome?: { runtime?: unknown; management?: unknown } })
        .chrome?.runtime ||
        (window as Window & { chrome?: { management?: unknown } }).chrome
          ?.management ||
        viaPassive.length > 0,
    );

  return { detected, scanSupported };
}

export async function detectVirtualCamera(
  activeStream?: MediaStream | null,
): Promise<VirtualCameraResult> {
  const suspiciousLabels: string[] = [];
  let maxScore = 0;
  const hasPermission = Boolean(activeStream);

  if (activeStream) {
    for (const track of activeStream.getVideoTracks()) {
      const label = track.label?.trim();
      const settings = track.getSettings?.() as MediaTrackSettingsEx | undefined;
      const score = scoreVirtualCameraSignal(label, settings, hasPermission);
      maxScore = Math.max(maxScore, score);
      if (label && score > 0 && !suspiciousLabels.includes(label)) {
        suspiciousLabels.push(label);
      } else if (!label && score > 0) {
        suspiciousLabels.push("(unlabeled camera)");
      }
    }
  }

  if (typeof navigator !== "undefined" && navigator.mediaDevices?.enumerateDevices) {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      for (const device of devices) {
        if (device.kind !== "videoinput") continue;
        const label = device.label?.trim();
        const score = scoreVirtualCameraSignal(label, undefined, hasPermission);
        maxScore = Math.max(maxScore, score);
        if (label && score > 0 && !suspiciousLabels.includes(label)) {
          suspiciousLabels.push(label);
        }
      }
    } catch {
      // enumerateDevices may fail without permission — rely on stream labels
    }
  }

  return buildVirtualCameraResult(suspiciousLabels, maxScore);
}

export function detectScreenSharingActive(
  activeStream?: MediaStream | null,
): boolean {
  if (!activeStream) return false;

  for (const track of activeStream.getVideoTracks()) {
    const settings = track.getSettings?.() as MediaTrackSettingsEx | undefined;
    if (settings?.displaySurface) {
      return true;
    }
    const label = track.label?.toLowerCase() ?? "";
    if (SCREEN_CAPTURE_LABEL_RE.test(label)) {
      return true;
    }
  }
  return false;
}

export async function detectScreenSharingCapability(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
    return false;
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.some(
      (device) =>
        device.kind === "videoinput" &&
        SCREEN_CAPTURE_LABEL_RE.test(device.label ?? ""),
    );
  } catch {
    return false;
  }
}

export async function scanInterviewEnvironment(
  activeStream?: MediaStream | null,
): Promise<EnvironmentScanResult> {
  const extensions = await detectScreenRecordingExtensions();
  const virtualCamera = await detectVirtualCamera(activeStream);
  const screenSharingActive = detectScreenSharingActive(activeStream);
  const screenSharingCapability = await detectScreenSharingCapability();

  return {
    extensions,
    virtualCamera,
    screenSharingActive,
    screenSharingCapability,
  };
}

export function extensionBlockMessage(ext: DetectedExtension): string {
  return `Please disable ${ext.name} before continuing`;
}
