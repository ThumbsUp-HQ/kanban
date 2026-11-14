import { describe, it, expect } from 'vitest';
import {
  bufferToBase64url,
  base64urlToBuffer,
  serializeAssertionCredential,
  serializeRegistrationCredential,
  isWebAuthnSupported,
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
  });

  it('detects isWebAuthnSupported based on window.PublicKeyCredential presence', () => {
    const originalPKC = (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential;
    const originalCreds = navigator.credentials;

    // Enabled state
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = function () {
      return undefined;
    };
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: {
        get: () => {
          return undefined;
        },
      },
    });
    expect(isWebAuthnSupported()).toBe(true);

    // Disabled state
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = undefined;
    expect(isWebAuthnSupported()).toBe(false);

    // Restore
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = originalPKC;
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: originalCreds,
    });
  });
});
