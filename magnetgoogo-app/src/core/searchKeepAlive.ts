import { NativeModules, Platform } from 'react-native';

type SearchKeepAliveNative = {
  start(title: string, text: string, token: number): Promise<boolean>;
  handoff(query: string, token: number, searchId: string): Promise<boolean>;
  stop(token: number): Promise<boolean>;
};

const nativeModule: SearchKeepAliveNative | undefined =
  Platform.OS === 'android' ? (NativeModules.SearchKeepAlive as SearchKeepAliveNative | undefined) : undefined;

const MAX_NATIVE_TOKEN = 2_147_483_646;
let _activeToken = 0;
let _tokenNonce = Math.floor(Math.random() * MAX_NATIVE_TOKEN) + 1;

function nextSearchToken(): number {
  const timePart = Date.now() % MAX_NATIVE_TOKEN;
  const randomPart = Math.floor(Math.random() * MAX_NATIVE_TOKEN);
  _tokenNonce = Math.floor((_tokenNonce + timePart + randomPart) % MAX_NATIVE_TOKEN) || 1;
  if (_tokenNonce === _activeToken) {
    _tokenNonce = (_tokenNonce % MAX_NATIVE_TOKEN) + 1;
  }
  return _tokenNonce;
}

export async function startSearchKeepAlive(query: string): Promise<number> {
  if (Platform.OS !== 'android' || !nativeModule?.start) {
    console.log('[SearchKeepAlive] native module unavailable');
    return 0;
  }
  const token = nextSearchToken();
  _activeToken = token;
  try {
    console.log(`[SearchKeepAlive] start token=${token} query=${query}`);
    await nativeModule.start('Search in progress', `Searching "${query}" in background`, token);
    return token;
  } catch {
    console.log(`[SearchKeepAlive] start failed token=${token}`);
    return 0;
  }
}

export async function stopSearchKeepAlive(token: number): Promise<void> {
  if (Platform.OS !== 'android' || !nativeModule?.stop) return;
  if (!token) return;
  if (token === _activeToken) _activeToken = 0;
  try {
    console.log(`[SearchKeepAlive] stop token=${token}`);
    await nativeModule.stop(token);
  } catch {
    // ignore
  }
}

export async function handoffSearchToBackground(
  query: string,
  token: number,
  searchId = '',
): Promise<boolean> {
  if (Platform.OS !== 'android' || !nativeModule?.handoff || !token || !query.trim()) return false;
  try {
    console.log(`[SearchKeepAlive] handoff token=${token} query=${query}`);
    return await nativeModule.handoff(query.trim(), token, searchId);
  } catch {
    return false;
  }
}
