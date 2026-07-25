// frontend/src/hooks/useExtensionDetection.ts

const KNOWN_RECORDING_EXTENSIONS: Record<string, string> = {
  liecbddmkiiihnedobmlmillhodjkdmb: "Loom",
  mmeijimgabbpbgpdklnllpncmdofkcpn: "Screencastify",
  bpconcjcammlapcogcnnelfmaeghhagj: "Nimbus Screenshot",
  hdiaamehgchmceplikhcgggiilllnhbl: "Nimbus Screenshot & Screen Video Recorder",
  kgbfjjfmaehgdmjkmkjpgellbdggnkhl: "Screen Recorder",
  jkpbjbdagkmhpibjgafbckclnkaaapca: "Awesome Screenshot",
};

const SCREEN_CAPTURE_LABEL_RE =
  /screen|display|monitor|window|desktop/i;

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

const EXPLICIT_VIRTUAL_CAMERA_RE =
  /\b(obs|manycam|droidcam|epoccam|xsplit|snap\s*camera|camo|mmhmm|nvidia\s*broadcast|virtual\s*cam(?:era)?)\b/i;

function labelLooksSuspicious(label: string): boolean {
  return EXPLICIT_VIRTUAL_CAMERA_RE.test(label);
}

function settingsLookVirtual(settings: MediaTrackSettingsEx | undefined): boolean {
  if (!settings) return false;
  // displaySurface means getDisplayMedia / screen share — not a normal webcam.
  return Boolean(settings.displaySurface);
}

function scoreVirtualCameraSignal(
  label: string | undefined,
  settings: MediaTrackSettingsEx | undefined,
): number {
  let score = 0;
  const trimmed = label?.trim() ?? "";

  if (trimmed && labelLooksSuspicious(trimmed)) {
    score += 80;
  }
  if (settings?.displaySurface) {
    score += 100;
  }
  if (trimmed && SCREEN_CAPTURE_LABEL_RE.test(trimmed) && !labelLooksSuspicious(trimmed)) {
    // "screen capture" style labels without explicit virtual-cam brands → soft signal only
    score += 25;
  }
  if (settingsLookVirtual(settings)) {
    score += 20;
  }
  return score;
}

function buildVirtualCameraResult(
  labels: string[],
  maxScore: number,
  options: {
    activeIsVirtual: boolean;
    unusedVirtualDevices: string[];
  },
): VirtualCameraResult {
  const { activeIsVirtual, unusedVirtualDevices } = options;
  // Hard block only when the live stream is a virtual / screen-capture camera.
  // Leftover drivers (e.g. uninstalled OBS still listed) are warn-only.
  const blockRecommended = activeIsVirtual || maxScore >= 100;
  const warnOnly =
    !blockRecommended && (unusedVirtualDevices.length > 0 || maxScore > 0);
  const confidence: VirtualCameraConfidence = blockRecommended
    ? "high"
    : warnOnly
      ? "low"
      : "none";
  const detected = confidence !== "none";

  let message: string | null = null;
  if (blockRecommended) {
    message =
      "Virtual camera is selected — switch to your real webcam (browser camera icon / site settings), then re-scan. If OBS was removed, restart the browser or reboot Windows so the old driver disappears.";
  } else if (warnOnly && unusedVirtualDevices.length > 0) {
    message =
      "A virtual camera driver is still listed on this PC (often leftover OBS). You can continue if your live preview is the real webcam. To clear the warning: uninstall OBS Virtual Camera, then restart Chrome.";
  } else if (warnOnly) {
    message =
      "Your camera setup looks unusual — if you are using a virtual camera, switch to your real webcam";
  }

  const deviceLabels = Array.from(
    new Set([...labels, ...unusedVirtualDevices].filter(Boolean)),
  );

  return {
    detected,
    confidence,
    blockRecommended,
    warnOnly,
    deviceLabels,
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
  const unusedVirtualDevices: string[] = [];
  let maxScore = 0;
  let activeIsVirtual = false;
  const activeLabels = new Set<string>();

  if (activeStream) {
    for (const track of activeStream.getVideoTracks()) {
      const label = track.label?.trim() ?? "";
      if (label) activeLabels.add(label);
      const settings = track.getSettings?.() as MediaTrackSettingsEx | undefined;
      const score = scoreVirtualCameraSignal(label || undefined, settings);
      maxScore = Math.max(maxScore, score);
      if (score >= 80 || settings?.displaySurface) {
        activeIsVirtual = true;
        if (label && !suspiciousLabels.includes(label)) {
          suspiciousLabels.push(label);
        } else if (!label) {
          suspiciousLabels.push("(unlabeled camera)");
        }
      }
    }
  }

  if (typeof navigator !== "undefined" && navigator.mediaDevices?.enumerateDevices) {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      for (const device of devices) {
        if (device.kind !== "videoinput") continue;
        const label = device.label?.trim();
        if (!label) continue;
        if (!labelLooksSuspicious(label)) continue;
        // Device exists but is not the one currently streaming → soft warning only.
        if (activeLabels.has(label)) {
          activeIsVirtual = true;
          if (!suspiciousLabels.includes(label)) suspiciousLabels.push(label);
        } else if (!unusedVirtualDevices.includes(label)) {
          unusedVirtualDevices.push(label);
        }
      }
    } catch {
      // enumerateDevices may fail without permission — rely on stream labels
    }
  }

  return buildVirtualCameraResult(suspiciousLabels, maxScore, {
    activeIsVirtual,
    unusedVirtualDevices,
  });
}

/** Prefer a physical webcam deviceId (skip OBS / virtual drivers when possible). */
export async function pickPreferredCameraDeviceId(): Promise<string | undefined> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
    return undefined;
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cams = devices.filter((d) => d.kind === "videoinput" && d.deviceId);
    if (cams.length === 0) return undefined;
    const real = cams.find((d) => !labelLooksSuspicious(d.label || ""));
    return (real ?? cams[0]).deviceId;
  } catch {
    return undefined;
  }
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
