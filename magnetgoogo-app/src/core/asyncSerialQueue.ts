export type AsyncTask<T> = () => Promise<T>;

/**
 * Serialize asynchronous operations while allowing each caller to receive its
 * own result or error. A rejected task never blocks later tasks.
 */
export function createAsyncSerialQueue() {
  let tail: Promise<void> = Promise.resolve();

  return function enqueue<T>(task: AsyncTask<T>): Promise<T> {
    const result = tail.then(task, task);
    tail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  };
}
