/**
 * Generic debounce utility.
 *
 * Returns a debounced wrapper around `fn` that only invokes `fn` after
 * `wait` milliseconds of silence. The wrapper also exposes a `cancel()`
 * method to clear any pending invocation.
 *
 * @example
 * const debouncedJog = debounce((v: number) => jog(robotId, { value_rad: v }), 50);
 */
export function debounce<Args extends unknown[]>(
  fn: (...args: Args) => void,
  wait: number,
): ((...args: Args) => void) & { cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | undefined;

  const debounced = (...args: Args): void => {
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      fn(...args);
    }, wait);
  };

  debounced.cancel = (): void => {
    if (timer !== undefined) {
      clearTimeout(timer);
      timer = undefined;
    }
  };

  return debounced;
}
