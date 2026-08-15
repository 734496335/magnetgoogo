export async function fetchAuthorityThenFallback<T>(
  authorityEndpoints: readonly string[],
  fallbackEndpoints: readonly string[],
  fetchAuthorityTier: (endpoints: readonly string[]) => Promise<T>,
  fetchFallbackEndpoint: (endpoint: string) => Promise<T>,
): Promise<T> {
  try {
    return await fetchAuthorityTier(authorityEndpoints);
  } catch (authorityError) {
    let lastError: unknown = authorityError;
    for (const endpoint of fallbackEndpoints) {
      try {
        return await fetchFallbackEndpoint(endpoint);
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError;
  }
}
