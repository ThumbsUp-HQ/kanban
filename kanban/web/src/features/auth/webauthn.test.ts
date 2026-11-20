import { describe, it, expect } from 'vitest';
import {
  bufferToBase64url,
  base64urlToBuffer,
  serializeAssertionCredential,
  serializeRegistrationCredential,
  isWebAuthnSupported,
  prepareCreationOptions,
  prepareRequestOptions,
} from './webauthn';

describe('webauthn base64url codecs & serializers (KB-P3-35)', () => {
  it('round-trips base64url <-> ArrayBuffer for lengths 0, 1, 32, 65 (Mandatory Test Case 7)', () => {
    const lengths = [0, 1, 32, 65];

    for (const len of lengths) {
      const originalBytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        // Varying byte values to test character boundaries, +, /, etc.
        originalBytes[i] = (i * 37 + 13) % 256;
      }

      // Test ArrayBuffer input
      const encoded = bufferToBase64url(originalBytes.buffer);
      // Test Uint8Array input directly
      const encodedFromUint8 = bufferToBase64url(originalBytes);
      expect(encoded).toBe(encodedFromUint8);
      // Base64url must not contain +, /, or =
      expect(encoded).not.toMatch(/[+/=]/);

      const decodedBuffer = base64urlToBuffer(encoded);
      const decodedBytes = new Uint8Array(decodedBuffer);

      expect(decodedBytes.length).toBe(len);
      for (let i = 0; i < len; i++) {
        expect(decodedBytes[i]).toBe(originalBytes[i]);
      }
    }
  });

  it('serializes PublicKeyCredential assertion response to JSON wire format', () => {
    const mockRawId = new Uint8Array([1, 2, 3, 4]).buffer;
    const mockClientDataJSON = new TextEncoder().encode('{"type":"webauthn.get"}').buffer;
    const mockAuthenticatorData = new Uint8Array([5, 6, 7, 8]).buffer;
    const mockSignature = new Uint8Array([9, 10, 11, 12]).buffer;
    const mockUserHandle = new Uint8Array([13, 14, 15, 16]).buffer;

    const mockCred = {
      id: 'mock-cred-id',
      rawId: mockRawId,
      type: 'public-key',
      response: {
        clientDataJSON: mockClientDataJSON,
        authenticatorData: mockAuthenticatorData,
        signature: mockSignature,
        userHandle: mockUserHandle,
      },
      getClientExtensionResults: () => ({ appid: true }),
    } as unknown as PublicKeyCredential;

    const serialized = serializeAssertionCredential(mockCred);

    expect(serialized.id).toBe('mock-cred-id');
    expect(serialized.type).toBe('public-key');
    expect(typeof serialized.rawId).toBe('string');
    expect(serialized.response.userHandle).toBe(bufferToBase64url(mockUserHandle));
    expect(serialized.clientExtensionResults).toEqual({ appid: true });
  });

  it('serializes assertion response with null userHandle', () => {
    const mockCred = {
      id: 'mock-cred-id-2',
      rawId: new Uint8Array([1]).buffer,
      type: 'public-key',
      response: {
        clientDataJSON: new Uint8Array([2]).buffer,
        authenticatorData: new Uint8Array([3]).buffer,
        signature: new Uint8Array([4]).buffer,
        userHandle: null,
      },
    } as unknown as PublicKeyCredential;

    const serialized = serializeAssertionCredential(mockCred);
    expect(serialized.response.userHandle).toBeNull();
    expect(serialized.clientExtensionResults).toEqual({});
  });

  it('serializes PublicKeyCredential registration response to JSON wire format', () => {
    const mockRawId = new Uint8Array([21, 22]).buffer;
    const mockClientDataJSON = new TextEncoder().encode('{"type":"webauthn.create"}').buffer;
    const mockAttestationObject = new Uint8Array([31, 32, 33]).buffer;

    const mockCred = {
      id: 'mock-reg-id',
      rawId: mockRawId,
      type: 'public-key',
      response: {
        clientDataJSON: mockClientDataJSON,
        attestationObject: mockAttestationObject,
        getTransports: () => ['internal', 'hybrid'],
      },
      getClientExtensionResults: () => ({}),
    } as unknown as PublicKeyCredential;

    const serialized = serializeRegistrationCredential(mockCred);

    expect(serialized.id).toBe('mock-reg-id');
    expect(serialized.type).toBe('public-key');
    expect(serialized.response.transports).toEqual(['internal', 'hybrid']);
    expect(serialized.response.attestationObject).toBe(bufferToBase64url(mockAttestationObject));

    // Registration credential without getTransports and without getClientExtensionResults
    const minimalCred = {
      id: 'min-reg-id',
      rawId: new Uint8Array([55]).buffer,
      type: 'public-key',
      response: {
        clientDataJSON: mockClientDataJSON,
        attestationObject: mockAttestationObject,
      },
    } as unknown as PublicKeyCredential;
    const minimalSerialized = serializeRegistrationCredential(minimalCred);
    expect(minimalSerialized.response.transports).toBeUndefined();
    expect(minimalSerialized.clientExtensionResults).toEqual({});
  });

  it('detects isWebAuthnSupported verifying isSecureContext, PublicKeyCredential, and credentials methods', () => {
    const originalPKC = (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential;
    const originalCreds = navigator.credentials;
    const originalSecure = window.isSecureContext;

    // Enabled state with all conditions satisfied
    Object.defineProperty(window, 'isSecureContext', {
      writable: true,
      configurable: true,
      value: true,
    });
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = function () {
      return undefined;
    };
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: {
        get: () => undefined,
        create: () => undefined,
      },
    });
    expect(isWebAuthnSupported()).toBe(true);

    // Disabled when isSecureContext is false
    Object.defineProperty(window, 'isSecureContext', {
      writable: true,
      configurable: true,
      value: false,
    });
    expect(isWebAuthnSupported()).toBe(false);

    // Restore secure context, disable PublicKeyCredential
    Object.defineProperty(window, 'isSecureContext', {
      writable: true,
      configurable: true,
      value: true,
    });
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = undefined;
    expect(isWebAuthnSupported()).toBe(false);

    // Restore PKC, disable create
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = function () {
      return undefined;
    };
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: {
        get: () => undefined,
      },
    });
    expect(isWebAuthnSupported()).toBe(false);

    // Disable get
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: {
        create: () => undefined,
      },
    });
    expect(isWebAuthnSupported()).toBe(false);

    // Restore original globals
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = originalPKC;
    Object.defineProperty(window, 'isSecureContext', {
      writable: true,
      configurable: true,
      value: originalSecure,
    });
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: originalCreds,
    });
  });

  it('prepares PublicKeyCredentialCreationOptions and PublicKeyCredentialRequestOptions', () => {
    const creationOptionsJson = {
      rp: { name: 'Kanban RP', id: 'localhost' },
      user: { id: bufferToBase64url(new Uint8Array([1, 2, 3])), name: 'alice', displayName: 'Alice' },
      challenge: bufferToBase64url(new Uint8Array([4, 5, 6])),
      pubKeyCredParams: [{ alg: -7, type: 'public-key' }],
      timeout: 30000,
      excludeCredentials: [
        { id: bufferToBase64url(new Uint8Array([7, 8, 9])), type: 'public-key', transports: ['usb'] },
      ],
      authenticatorSelection: { authenticatorAttachment: 'platform' as const, userVerification: 'required' as const },
      attestation: 'none' as const,
    };

    const preparedCreation = prepareCreationOptions(creationOptionsJson);
    expect(preparedCreation.rp.name).toBe('Kanban RP');
    expect(preparedCreation.user.id.byteLength).toBe(3);
    expect(preparedCreation.challenge.byteLength).toBe(3);
    expect(preparedCreation.pubKeyCredParams).toEqual([{ alg: -7, type: 'public-key' }]);
    expect(preparedCreation.timeout).toBe(30000);
    expect(preparedCreation.excludeCredentials?.[0]?.id.byteLength).toBe(3);
    expect(preparedCreation.excludeCredentials?.[0]?.transports).toEqual(['usb']);
    expect(preparedCreation.authenticatorSelection?.authenticatorAttachment).toBe('platform');
    expect(preparedCreation.attestation).toBe('none');

    // Also without transports on credential descriptor
    const preparedWithoutTransports = prepareCreationOptions({
      rp: { name: 'Kanban RP' },
      user: { id: bufferToBase64url(new Uint8Array([1])), name: 'bob', displayName: 'Bob' },
      challenge: bufferToBase64url(new Uint8Array([2])),
      pubKeyCredParams: [],
      excludeCredentials: [{ id: bufferToBase64url(new Uint8Array([3])), type: 'public-key' }],
    });
    expect(preparedWithoutTransports.excludeCredentials?.[0]?.transports).toBeUndefined();

    // Also with optional fields omitted
    const minimalCreation = prepareCreationOptions({
      rp: { name: 'Kanban RP' },
      user: { id: bufferToBase64url(new Uint8Array([1])), name: 'bob', displayName: 'Bob' },
      challenge: bufferToBase64url(new Uint8Array([2])),
      pubKeyCredParams: [],
    });
    expect(minimalCreation.timeout).toBe(60000);
    expect(minimalCreation.excludeCredentials).toBeUndefined();

    // Prepare Request options
    const requestOptionsJson = {
      challenge: bufferToBase64url(new Uint8Array([10, 11, 12])),
      timeout: 45000,
      rpId: 'localhost',
      allowCredentials: [
        { id: bufferToBase64url(new Uint8Array([13, 14])), type: 'public-key', transports: ['internal'] },
        { id: bufferToBase64url(new Uint8Array([15, 16])), type: 'public-key' },
      ],
      userVerification: 'required' as const,
    };

    const preparedRequest = prepareRequestOptions(requestOptionsJson);
    expect(preparedRequest.challenge.byteLength).toBe(3);
    expect(preparedRequest.timeout).toBe(45000);
    expect(preparedRequest.rpId).toBe('localhost');
    expect(preparedRequest.userVerification).toBe('required');
    expect(preparedRequest.allowCredentials?.[0]?.id.byteLength).toBe(2);
    expect(preparedRequest.allowCredentials?.[0]?.transports).toEqual(['internal']);
    expect(preparedRequest.allowCredentials?.[1]?.transports).toBeUndefined();

    // Minimal request options
    const minimalRequest = prepareRequestOptions({
      challenge: bufferToBase64url(new Uint8Array([99])),
    });
    expect(minimalRequest.timeout).toBe(60000);
    expect(minimalRequest.userVerification).toBe('preferred');
    expect(minimalRequest.rpId).toBeUndefined();
    expect(minimalRequest.allowCredentials).toBeUndefined();
  });
});
