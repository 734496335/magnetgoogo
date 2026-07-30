import * as FileSystem from 'expo-file-system/legacy';
import { getUpdateErrorMessage } from './updateDownloadPolicy';

const MIN_APK_BYTES = 5 * 1024 * 1024;

export interface UpdateDownloadProgress {
  url: string;
  bytesWritten: number;
  totalBytes: number;
  ratio: number;
}

export interface UpdateDownloadResult {
  uri: string;
  url: string;
}

export interface UpdateDownloadOptions {
  candidates: string[];
  fileUri: string;
  onProgress?: (progress: UpdateDownloadProgress) => void;
  onAttempt?: (url: string, index: number, total: number) => void;
}

async function removeExistingFile(fileUri: string): Promise<void> {
  const info = await FileSystem.getInfoAsync(fileUri);
  if (info.exists) await FileSystem.deleteAsync(fileUri, { idempotent: true });
}

async function assertDownloadedApk(fileUri: string): Promise<void> {
  const info = await FileSystem.getInfoAsync(fileUri);
  const size = info.exists && 'size' in info && typeof info.size === 'number' ? info.size : 0;
  if (!info.exists || size < MIN_APK_BYTES) {
    throw new Error(`invalid_apk_size:${size}`);
  }

  const prefix = await FileSystem.readAsStringAsync(fileUri, {
    encoding: FileSystem.EncodingType.Base64,
    position: 0,
    length: 4,
  });
  if (!prefix.startsWith('UEsDBA')) {
    throw new Error('invalid_apk_signature');
  }
}

/**
 * Download from direct APK candidates in order. A failed candidate is discarded
 * before the next one starts, so an HTML error page can never be installed as APK.
 */
export async function downloadApkFromCandidates(options: UpdateDownloadOptions): Promise<UpdateDownloadResult> {
  const { candidates, fileUri, onProgress, onAttempt } = options;
  const failures: string[] = [];

  for (let index = 0; index < candidates.length; index += 1) {
    const url = candidates[index];
    onAttempt?.(url, index, candidates.length);

    try {
      await removeExistingFile(fileUri);
      const download = FileSystem.createDownloadResumable(
        url,
        fileUri,
        {},
        (event) => {
          const totalBytes = Math.max(0, event.totalBytesExpectedToWrite || 0);
          const bytesWritten = Math.max(0, event.totalBytesWritten || 0);
          const ratio = totalBytes > 0 ? Math.min(1, bytesWritten / totalBytes) : 0;
          onProgress?.({ url, bytesWritten, totalBytes, ratio });
        },
      );

      const result = await download.downloadAsync();
      if (!result?.uri) throw new Error('download_empty_result');
      await assertDownloadedApk(result.uri);
      return { uri: result.uri, url };
    } catch (error: unknown) {
      const message = getUpdateErrorMessage(error);
      failures.push(`${url}:${message}`);
      console.log('[UpdateDownload]', JSON.stringify({
        rule_id: 'app_update_download',
        stage: 'candidate_failed',
        error_code: message.split(':')[0] || 'download_failed',
        candidate_index: index,
        candidate_count: candidates.length,
        url,
      }));
    }
  }

  await removeExistingFile(fileUri).catch((error: unknown) => {
    console.log('[UpdateDownload]', JSON.stringify({
      rule_id: 'app_update_download',
      stage: 'cleanup_failed',
      error_code: 'cache_cleanup_failed',
      message: getUpdateErrorMessage(error),
    }));
  });
  throw new Error(`all_download_candidates_failed:${failures.join('|')}`);
}
