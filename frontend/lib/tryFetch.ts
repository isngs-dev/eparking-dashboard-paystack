import { BackendFetchError } from "./api/backendFetch";

export interface FetchResult<T> {
  data: T | null;
  errorMessage: string | null;
}

/**
 * Catches a backendFetch call locally within the visual's own async Server
 * Component and returns a plain result object instead of letting the error
 * cross the RSC server/client boundary to be caught by a class-based error
 * boundary -- that crossing was verified unreliable for errors thrown during
 * an async Server Component's data-fetching phase (Next.js redacts the
 * error to a bare digest and a wrapping client `<VisualErrorBoundary>`'s
 * fallback did not reliably render for this exact pattern in manual
 * testing). Catching per-visual, per-call is what actually guarantees the
 * sprint's per-visual isolation requirement.
 */
export async function tryFetch<T>(fn: () => Promise<T>): Promise<FetchResult<T>> {
  try {
    const data = await fn();
    return { data, errorMessage: null };
  } catch (err) {
    const message =
      err instanceof BackendFetchError
        ? err.detail
        : err instanceof Error
          ? err.message
          : "Something went wrong.";
    return { data: null, errorMessage: message };
  }
}
