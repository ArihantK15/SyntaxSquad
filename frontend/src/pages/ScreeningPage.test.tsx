import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ScreeningPage } from './ScreeningPage';
import { api } from '../services/api';

vi.mock('../services/api', () => ({
  api: {
    uploadScreeningDocument: vi.fn(),
    runStepOCR: vi.fn(),
    runStepValidate: vi.fn(),
    runStepTamper: vi.fn(),
    runStepFace: vi.fn(),
    runStepRisk: vi.fn(),
    generateSpecimenDoc: vi.fn(),
  },
}));

const noop = () => {};

function jpegFile(name = 'document.jpg'): File {
  return new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0])], name, { type: 'image/jpeg' });
}

function textFile(name = 'not_an_image.txt'): File {
  const bytes = Array.from(new TextEncoder().encode('This is not an image file.'));
  return new File([new Uint8Array(bytes)], name, { type: 'image/jpeg' }); // mislabeled on purpose
}

describe('ScreeningPage document upload', () => {
  beforeEach(() => {
    vi.mocked(api.uploadScreeningDocument).mockReset();
    // jsdom's real URL.createObjectURL chokes on File objects built from a
    // typed array (unrelated to the fix under test), so stub it the way a
    // real browser would just work.
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:mock-preview') });
  });

  it('rejects a non-image file with an inline error instead of accepting it', async () => {
    // Reproduces the reported freeze: a .txt file uploaded via the document
    // dropzone used to be accepted with no validation, enabling the Run
    // button, and only failed once the pipeline actually started -- via a
    // blocking window.alert() that froze the tab. It must now be rejected
    // immediately, inline, before the Run button ever becomes usable.
    render(<ScreeningPage onScreeningComplete={noop} />);

    const input = screen.getByTestId('doc-file-input') as HTMLInputElement;
    await userEvent.upload(input, textFile());

    await waitFor(() => {
      expect(screen.getByText(/doesn't look like a JPEG or PNG/i)).toBeInTheDocument();
    });

    // No broken preview, and the pipeline must never have been reachable.
    expect(screen.queryByAltText('Document Preview')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run full ai screening pipeline/i })).toBeDisabled();
    expect(api.uploadScreeningDocument).not.toHaveBeenCalled();
  });

  it('accepts a real image file and enables the Run button', async () => {
    render(<ScreeningPage onScreeningComplete={noop} />);

    const input = screen.getByTestId('doc-file-input') as HTMLInputElement;
    await userEvent.upload(input, jpegFile());

    await waitFor(() => {
      expect(screen.getByAltText('Document Preview')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /run full ai screening pipeline/i })).toBeEnabled();
  });

  it('surfaces a pipeline failure as an inline error and marks the failing stage, never a blocking alert', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.mocked(api.uploadScreeningDocument).mockRejectedValue(new Error('Invalid file extension: .txt'));

    render(<ScreeningPage onScreeningComplete={noop} />);

    const input = screen.getByTestId('doc-file-input') as HTMLInputElement;
    await userEvent.upload(input, jpegFile());
    await waitFor(() => expect(screen.getByRole('button', { name: /run full ai screening pipeline/i })).toBeEnabled());

    await userEvent.click(screen.getByRole('button', { name: /run full ai screening pipeline/i }));

    await waitFor(() => {
      // Surfaces twice by design: once as the persistent error banner, once
      // as the failed pipeline stage's own detail text (see ProcessingPipeline).
      expect(screen.getAllByText(/invalid file extension/i).length).toBeGreaterThan(0);
    });
    expect(alertSpy).not.toHaveBeenCalled();
    // The Run button must be usable again, not stuck disabled forever.
    expect(screen.getByRole('button', { name: /run full ai screening pipeline/i })).toBeEnabled();

    alertSpy.mockRestore();
  });
});
