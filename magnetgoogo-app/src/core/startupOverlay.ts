import { NativeModules, Platform } from 'react-native';

type StartupOverlayNative = {
  hide: () => Promise<boolean>;
};

const nativeModule: StartupOverlayNative | undefined =
  Platform.OS === 'android'
    ? (NativeModules.StartupOverlay as StartupOverlayNative | undefined)
    : undefined;

export async function hideStartupOverlay(): Promise<void> {
  if (!nativeModule?.hide) return;
  try {
    await nativeModule.hide();
  } catch (error) {
    console.warn('[StartupOverlay]', {
      stage: 'hide_native_overlay',
      error_code: 'STARTUP_OVERLAY_HIDE_FAILED',
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
