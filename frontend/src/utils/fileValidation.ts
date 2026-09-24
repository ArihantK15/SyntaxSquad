// A file's declared MIME type (File.type) and extension are both just
// labels the browser trusts from the OS/drag source -- neither is checked
// against the actual bytes. Feeding a mislabeled file (e.g. a .txt renamed
// or dropped straight into an <input accept="image/*">) straight into the
// screening pipeline sent it to the backend, which rejected it, but the
// resulting error surfaced through a blocking window.alert() -- effectively
// freezing the tab for anyone driving it (including automated testing).
// Checking the real file signature client-side, before any of that, lets
// New Screening reject it instantly with an inline message instead.
const JPEG_MAGIC = [0xff, 0xd8, 0xff];
const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

async function readMagicBytes(file: File, length: number): Promise<Uint8Array> {
  const buffer = await file.slice(0, length).arrayBuffer();
  return new Uint8Array(buffer);
}

function matchesSignature(bytes: Uint8Array, signature: number[]): boolean {
  if (bytes.length < signature.length) return false;
  return signature.every((b, i) => bytes[i] === b);
}

export interface FileValidationResult {
  valid: boolean;
  reason?: string;
}

/**
 * Validates that `file` is really a JPEG or PNG by inspecting its leading
 * bytes, not just its extension or declared MIME type.
 */
export async function validateImageFile(file: File): Promise<FileValidationResult> {
  if (file.size === 0) {
    return { valid: false, reason: 'That file is empty (0 bytes).' };
  }

  let bytes: Uint8Array;
  try {
    bytes = await readMagicBytes(file, 8);
  } catch {
    return { valid: false, reason: 'Could not read that file. It may be corrupted or inaccessible.' };
  }

  if (matchesSignature(bytes, JPEG_MAGIC) || matchesSignature(bytes, PNG_MAGIC)) {
    return { valid: true };
  }

  return {
    valid: false,
    reason: `"${file.name}" doesn't look like a JPEG or PNG image (its content doesn't match either file signature). Please choose a real image file.`
  };
}
