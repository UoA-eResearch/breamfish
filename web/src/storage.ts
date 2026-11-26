// Remembered choices (area, fishing style, map layer). Stored in this browser only.

export function stored(key: string): string | null {
  try {
    return localStorage.getItem(`breamfish.${key}`);
  } catch {
    return null;
  }
}

export function store(key: string, value: string): void {
  try {
    localStorage.setItem(`breamfish.${key}`, value);
  } catch {
    // Private windows may refuse storage; the choice just won't be remembered.
  }
}
