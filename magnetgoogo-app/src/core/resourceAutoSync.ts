import type { MediaKind, MovieFeed } from './resourceFeedProtocol';

export const RESOURCE_AUTO_SYNC_MIN_INTERVAL_MS = 60_000;
export const RESOURCE_AUTO_SYNC_FOREGROUND_INTERVAL_MS = 15 * 60_000;

export function resourceFeedReleaseId(feed: MovieFeed): string | null {
  return feed.items.find((item) => item.remote_release_id)?.remote_release_id ?? null;
}

export function sameRemoteResourceRelease(left: MovieFeed, right: MovieFeed): boolean {
  const leftReleaseId = resourceFeedReleaseId(left);
  const rightReleaseId = resourceFeedReleaseId(right);
  return leftReleaseId !== null && rightReleaseId !== null && leftReleaseId === rightReleaseId;
}

/**
 * Small focus/foreground revalidation gate.
 *
 * Failed attempts are deliberately NOT put on cooldown: the next focus or
 * foreground event must be allowed to retry. Only a successful network sync
 * starts the cooldown.
 */
export class ResourceAutoSyncGate {
  private readonly inFlight = new Set<MediaKind>();
  private readonly lastSuccessAt: Partial<Record<MediaKind, number>> = {};

  tryStart(kind: MediaKind, now = Date.now()): boolean {
    if (this.inFlight.has(kind)) return false;
    const lastSuccessAt = this.lastSuccessAt[kind];
    if (lastSuccessAt !== undefined) {
      const elapsed = now - lastSuccessAt;
      if (elapsed >= 0 && elapsed < RESOURCE_AUTO_SYNC_MIN_INTERVAL_MS) return false;
    }
    this.inFlight.add(kind);
    return true;
  }

  complete(kind: MediaKind, succeeded: boolean, now = Date.now()): void {
    this.inFlight.delete(kind);
    if (succeeded) this.lastSuccessAt[kind] = now;
  }

  markSuccess(kind: MediaKind, now = Date.now()): void {
    this.lastSuccessAt[kind] = now;
  }
}
