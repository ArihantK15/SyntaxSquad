import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from './api';

const OFFICER_KEY_STORAGE = 'bordermesh_officer_key';

describe('officer-gated requests', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('prompts for the officer password and sends it as X-API-Key when none is stored yet', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('correct-password');
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ message: 'ok' }), { status: 200 }));

    await api.deleteCase('case-1');

    expect(promptSpy).toHaveBeenCalledTimes(1);
    const [, options] = fetchSpy.mock.calls[0];
    expect((options?.headers as Record<string, string>)['X-API-Key']).toBe('correct-password');
  });

  it('reuses the session-stored password on a later officer-gated call without re-prompting', async () => {
    sessionStorage.setItem(OFFICER_KEY_STORAGE, 'already-entered');
    const promptSpy = vi.spyOn(window, 'prompt');
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ message: 'ok' }), { status: 200 }));

    await api.deleteCase('case-1');

    expect(promptSpy).not.toHaveBeenCalled();
    const [, options] = fetchSpy.mock.calls[0];
    expect((options?.headers as Record<string, string>)['X-API-Key']).toBe('already-entered');
  });

  it('drops a stale stored password and re-prompts exactly once when the server rejects it with 401', async () => {
    sessionStorage.setItem(OFFICER_KEY_STORAGE, 'stale-password');
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('fresh-password');
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Missing or invalid X-API-Key for this action.' }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: 'ok' }), { status: 200 }));

    await api.deleteCase('case-1');

    expect(promptSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    const [, retryOptions] = fetchSpy.mock.calls[1];
    expect((retryOptions?.headers as Record<string, string>)['X-API-Key']).toBe('fresh-password');
    expect(sessionStorage.getItem(OFFICER_KEY_STORAGE)).toBe('fresh-password');
  });

  it('never calls fetch at all if the officer cancels the password prompt', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue(null);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    await expect(api.deleteCase('case-1')).rejects.toThrow(/officer authorization/i);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('applies the same officer-key handling to biometric purge, chain anchoring, and policy updates', async () => {
    sessionStorage.setItem(OFFICER_KEY_STORAGE, 'shared-session-password');
    const promptSpy = vi.spyOn(window, 'prompt');
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () => new Response(JSON.stringify({ message: 'ok' }), { status: 200 }));

    await api.purgeBiometrics('case-1');
    await api.anchorAuditChain();
    await api.updatePolicy({} as any);

    expect(promptSpy).not.toHaveBeenCalled();
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    for (const call of fetchSpy.mock.calls) {
      const [, options] = call;
      expect((options?.headers as Record<string, string>)['X-API-Key']).toBe('shared-session-password');
    }
  });
});
