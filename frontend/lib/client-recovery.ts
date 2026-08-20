export const RECOVERY_ATTEMPT_KEY = "ai-stock-recovery-attempt-v1";

type RecoveryAttempt = {
  fingerprint: string;
  timestamp: number;
};

const RECOVERY_WINDOW_MS = 60_000;


export function clearRecoveryAttempt(): void {
  try {
    window.sessionStorage.removeItem(RECOVERY_ATTEMPT_KEY);
  } catch {
    // Some in-app or private browsers disable web storage entirely.
  }
}


export function markFirstRecoveryAttempt(
  fingerprint: string,
): boolean {
  try {
    const now = Date.now();
    const stored = window.sessionStorage.getItem(RECOVERY_ATTEMPT_KEY);

    if (stored) {
      try {
        const parsed = JSON.parse(stored) as Partial<RecoveryAttempt>;
        if (
          parsed.fingerprint === fingerprint &&
          typeof parsed.timestamp === "number" &&
          now - parsed.timestamp < RECOVERY_WINDOW_MS
        ) {
          return false;
        }
      } catch {
        // Replace a malformed marker below instead of disabling recovery.
      }
    }

    const attempt: RecoveryAttempt = {
      fingerprint,
      timestamp: now,
    };
    window.sessionStorage.setItem(
      RECOVERY_ATTEMPT_KEY,
      JSON.stringify(attempt),
    );
    return true;
  } catch {
    return false;
  }
}
