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
];

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
  deviceLabels: string[];
  message: string | null;
}

export interface EnvironmentScanResult {
  extensions: ExtensionScanResult;
  virtualCamera: VirtualCameraResult;
  screenSharingActive: boolean;
}

type ChromeManagementExtension = {
  id: string;
  name?: string;
  enabled?: boolean;
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

async function detectExtensionsViaConnect(): Promise<DetectedExtension[]> {
  const detected: DetectedExtension[] = [];

  if (typeof window === "undefined" || !(window as Window & { chrome?: { runtime?: unknown } }).chrome?.runtime) {
    return detected;
  }

  const runtime = (window as unknown as {
    chrome: { runtime: { connect: (id: string) => { disconnect: () => void } } };
  }).chrome.runtime;

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
  const chromeApi = (window as Window & {
    chrome?: {
      management?: {
        getAll: (
          cb: (items: ChromeManagementExtension[]) => void,
        ) => void;
      };
    };
  }).chrome;

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
          if (lower.includes("record") || lower.includes("screen")) {
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
  const detected = mergeExtensions(viaConnect, viaManagement);

  const scanSupported =
    typeof window !== "undefined" &&
    Boolean(
      (window as Window & { chrome?: { runtime?: unknown; management?: unknown } })
        .chrome?.runtime ||
        (window as Window & { chrome?: { management?: unknown } }).chrome
          ?.management,
    );

  return { detected, scanSupported };
}

export async function detectVirtualCamera(
  activeStream?: MediaStream | null,
): Promise<VirtualCameraResult> {
  const suspiciousLabels: string[] = [];

  if (activeStream) {
    for (const track of activeStream.getVideoTracks()) {
      const label = track.label?.trim();
      if (label && labelLooksSuspicious(label) && !suspiciousLabels.includes(label)) {
        suspiciousLabels.push(label);
      }
      const settings = track.getSettings?.() as MediaTrackSettings & {
        displaySurface?: string;
      };
      if (settings?.displaySurface && label && !suspiciousLabels.includes(label)) {
        suspiciousLabels.push(label);
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
        if (labelLooksSuspicious(label) && !suspiciousLabels.includes(label)) {
          suspiciousLabels.push(label);
        }
      }
    } catch {
      // enumerateDevices may fail without permission — rely on stream labels
    }
  }

  const detected = suspiciousLabels.length > 0;
  return {
    detected,
    deviceLabels: suspiciousLabels,
    message: detected
      ? "Virtual camera detected - please use your real webcam"
      : null,
  };
}

export function detectScreenSharingActive(
  activeStream?: MediaStream | null,
): boolean {
  if (!activeStream) return false;

  for (const track of activeStream.getVideoTracks()) {
    const settings = track.getSettings?.() as MediaTrackSettings & {
      displaySurface?: string;
    };
    if (settings?.displaySurface) {
      return true;
    }
  }
  return false;
}

export async function scanInterviewEnvironment(
  activeStream?: MediaStream | null,
): Promise<EnvironmentScanResult> {
  const extensions = await detectScreenRecordingExtensions();
  const virtualCamera = await detectVirtualCamera(activeStream);
  const screenSharingActive = detectScreenSharingActive(activeStream);

  return {
    extensions,
    virtualCamera,
    screenSharingActive,
  };
}

export function extensionBlockMessage(ext: DetectedExtension): string {
  return `Please disable ${ext.name} before continuing`;
}
