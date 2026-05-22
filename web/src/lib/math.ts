/**
 * Lightweight math helpers for the vision pipeline.
 *
 * Kept minimal — no external deps, pure TypeScript.
 */

/**
 * Convert a unit quaternion [w, x, y, z] to a 3x3 rotation matrix
 * in row-major order (same convention as OpenCV).
 *
 * @example
 *   quatToRotMatrix([1, 0, 0, 0])
 *   // => [[1,0,0],[0,1,0],[0,0,1]]
 */
export function quatToRotMatrix(
  q: [number, number, number, number],
): [[number, number, number], [number, number, number], [number, number, number]] {
  const [w, x, y, z] = q;
  return [
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
  ];
}
