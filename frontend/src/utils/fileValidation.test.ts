import { describe, it, expect } from 'vitest';
import { validateImageFile } from './fileValidation';

function fileFromBytes(bytes: number[], name: string, type: string): File {
  return new File([new Uint8Array(bytes)], name, { type });
}

describe('validateImageFile', () => {
  it('accepts a real JPEG (FF D8 FF signature)', async () => {
    const file = fileFromBytes([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46], 'photo.jpg', 'image/jpeg');
    const result = await validateImageFile(file);
    expect(result.valid).toBe(true);
  });

  it('accepts a real PNG signature', async () => {
    const file = fileFromBytes([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 'photo.png', 'image/png');
    const result = await validateImageFile(file);
    expect(result.valid).toBe(true);
  });

  it('rejects a plain text file even when named/typed like an image', async () => {
    // Reproduces the real bug: a .txt file uploaded through New Screening
    // was accepted with no content check, sent straight to the pipeline,
    // and the resulting server-side rejection surfaced through a blocking
    // window.alert() that froze the tab. This must be caught here, before
    // any of that.
    const bytes = Array.from(new TextEncoder().encode('This is not an image file.'));
    const file = fileFromBytes(bytes, 'not_an_image.txt', 'image/jpeg');
    const result = await validateImageFile(file);
    expect(result.valid).toBe(false);
    expect(result.reason).toMatch(/doesn't look like a JPEG or PNG/i);
  });

  it('rejects an empty file', async () => {
    const file = fileFromBytes([], 'empty.jpg', 'image/jpeg');
    const result = await validateImageFile(file);
    expect(result.valid).toBe(false);
    expect(result.reason).toMatch(/empty/i);
  });

  it('rejects a file whose declared MIME type is image but whose bytes are not', async () => {
    // File.type is just a label the browser attaches from the extension --
    // never trust it over the actual bytes.
    const file = fileFromBytes([0x25, 0x50, 0x44, 0x46], 'fake.jpg', 'image/jpeg'); // %PDF header
    const result = await validateImageFile(file);
    expect(result.valid).toBe(false);
  });
});
