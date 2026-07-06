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
