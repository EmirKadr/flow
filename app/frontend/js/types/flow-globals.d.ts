// Typkontrakt för flow-frontendens globala yta. Ingen runtime-kod — filen
// läses bara av tsc (npm run typecheck) och editorn. Växer i takt med
// @ts-check-utrullningen. API-svarens former ska hållas i synk med
// app/backend/schemas.py i samma arbetsinsats som schemat ändras.

/** Fel kastade av api.* — Error utökad med HTTP-status och svarskropp. */
interface ApiError extends Error {
  status?: number;
  path?: string;
  body?: unknown;
  originalError?: unknown;
}

/** Options för api.get/post/put/del/download (utöver fetch:s RequestInit). */
interface ApiRequestOptions extends RequestInit {
  headers?: Record<string, string>;
  cacheTtlMs?: number;
  skipCache?: boolean;
  logLabel?: string;
  logUserEvent?: boolean;
  logGetUserEvent?: boolean;
  logSuccess?: boolean;
  logFailure?: boolean;
  telemetryEnabled?: boolean;
  telemetryEventType?: string;
  telemetrySource?: string;
  traceparent?: string;
  filename?: string;
}

interface FlowLogTarget {
  append?: (message: string, kind?: string, title?: string) => void;
  info?: (message: string, title?: string) => void;
  success?: (message: string, title?: string) => void;
  warn?: (message: string, title?: string) => void;
  error?: (message: string, title?: string) => void;
  clear?: () => void;
}

interface Window {
  // Telemetri/tracking (definieras i common/-lagret; optional eftersom alla
  // sidor inte laddar alla script).
  flowRecordWaitMetric?: (payload: Record<string, unknown>) => void;
  flowCurrentInteractionContext?: () => Record<string, any> | null;
  flowTrack?: (eventType: string, payload: Record<string, unknown>) => void;
  flowLog?: FlowLogTarget;
  appendAppLog?: (message: string, kind?: string, title?: string) => void;
  // Publika ytor som api.js exponerar för andra script och desktop-bryggan.
  api?: any;
  reportApiError?: (path: string, detail?: Record<string, unknown>) => void;
  // Sidspecifika prefetch-krokar (definieras av respektive domän-boot).
  preloadAllocationUploadsData?: () => void;
  // Etiketteditorns symbolkatalog, streckkoder och ritverktyg (label_editor/).
  FlowLabelSymbols?: any;
  FlowLabelBarcodes?: any;
  FlowLabelPaint?: any;
  // Buggrapportering (common/bug_report.js, lazy-laddad) + vendrad rrweb.
  flowBugReport?: { open: () => void; isRecording: () => boolean };
  rrweb?: {
    record: (options: Record<string, unknown>) => (() => void) | undefined;
    Replayer: new (events: unknown[], options?: Record<string, unknown>) => {
      play: (offsetMs?: number) => void;
      pause: () => void;
    };
  };
  // Sidkontext och desktop-brygga (sätts av foundation/desktop-skalet).
  flowActivePage?: string;
  flowCurrentViewId?: string;
  flowDesktop?: {
    isDesktop?: () => boolean;
    ready?: () => Promise<any>;
    pickFiles?: (options?: { accept?: string; multiple?: boolean }) => Promise<any[]>;
  };
  flowDesktopBridge?: any;
  qt?: { webChannelTransport?: unknown };
  QWebChannel?: any;
  // Behörighets- och layoutkonstanter som common.js exponerar globalt.
  ROLE_VIEW_ROLES?: any;
  ROLE_VIEW_LEVELS?: any;
  ROLE_VIEW_IDS?: any;
  SIDEBAR_DEFAULT_LAYOUT?: any;
  flowFlushWaitMetrics?: (...args: any[]) => any;
  flowFlushInteractions?: (...args: any[]) => any;
  sharedAllocationUploads?: {
    saveFiles: (...args: any[]) => any;
    clearGeneration: (...args: any[]) => any;
  };
  flowBackgroundPrefetch?: {
    status: () => any;
    waitForIdle: (...args: any[]) => any;
  };
  allocationUploadActivity?: {
    start: (...args: any[]) => any;
    finish: (...args: any[]) => any;
    clear: (...args: any[]) => any;
  };
  // Periodväljaren (common/period_picker.js).
  flowPeriodPicker?: {
    open: (options: {
      period?: string;
      anchorEl?: HTMLElement | null;
      currentIso?: string;
      onPick?: (value: string) => void;
    }) => void;
    close: () => void;
  };
}
