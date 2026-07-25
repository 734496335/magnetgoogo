/**
 * Test Logger — writes structured search results to shared storage.
 * Used by the K30S automation script to collect results via ADB.
 * Only active in __DEV__ mode.
 */
import * as FileSystem from 'expo-file-system/legacy';

// Write to shared external storage (accessible via ADB without root)
const BASE_DIR = FileSystem.cacheDirectory || FileSystem.documentDirectory || '';
const LOG_FILE = BASE_DIR + 'test-results.jsonl';
const DONE_FILE = BASE_DIR + 'test-done.json';

export async function logSourceResult(entry: {
  id: string; origin: string; handler: string;
  results: number; ms: number; status: string;
}) {
  if (!__DEV__) return;
  try {
    const line = JSON.stringify({ ...entry, ts: Date.now() }) + '\n';
    let existing = '';
    try { existing = await FileSystem.readAsStringAsync(LOG_FILE); } catch {}
    await FileSystem.writeAsStringAsync(LOG_FILE, existing + line);
  } catch (e) {
    // Silently fail - don't break search for logging
  }
}

export async function markSearchDone(query: string, totalResults: number, elapsedMs: number) {
  if (!__DEV__) return;
  try {
    await FileSystem.writeAsStringAsync(DONE_FILE, JSON.stringify({
      query, totalResults, elapsedMs, doneAt: Date.now(),
    }));
  } catch {}
}

export async function clearTestLog() {
  if (!__DEV__) return;
  try {
    await FileSystem.writeAsStringAsync(LOG_FILE, '');
    await FileSystem.deleteAsync(DONE_FILE, { idempotent: true });
  } catch {}
}

export { LOG_FILE, DONE_FILE };
