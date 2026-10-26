// FE-05: Sign in with Google. The button is a plain link to the API's /auth/google/start (a
// full page load, not fetch); errors come back as /login?error=<code> (BE-15).

export const GOOGLE_ERRORS: Record<string, string> = {
  google_cancelled: "Google sign-in was cancelled. Try again, or use an email code below.",
  google_not_allowed:
    "This Google account can't sign in here. Use your BTU Google account (name@btu.edu.ge), or an email code below.",
  google_unavailable: "Google can't be reached right now. Try again shortly, or use an email code below.",
  google_failed: "Google sign-in didn't complete. Try again, or use an email code below.",
  google_rate_limited: "Too many sign-in attempts. Try again later, or use an email code below.",
};

/** The message for a /login?error= code, or null for no (or an unknown) code. */
export function googleErrorMessage(code: string | null | undefined): string | null {
  return (code && GOOGLE_ERRORS[code]) || null;
}

/** Where the button goes; `next` is passed on and validated by the API. */
export function googleStartUrl(next?: string): string {
  return next ? `/auth/google/start?${new URLSearchParams({ next })}` : "/auth/google/start";
}
