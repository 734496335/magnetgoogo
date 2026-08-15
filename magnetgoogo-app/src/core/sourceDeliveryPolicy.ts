export async function fetchAuthorityThenFallback<T>(
  authorityEndpoints: readonly string[],
  fallbackEndpoints: readonly string[],
  fetchEndpoint: (endpoint: string) => Promise<T>,
): Promise<T> {
  let lastError: unknown = new Error('no_source_endpoint_available');
  for (const endpoint of [...authorityEndpoints, ...fallbackEndpoints]) {
    try {
      return await fetchEndpoint(endpoint);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}
