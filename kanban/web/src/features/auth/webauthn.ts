/**
 * WebAuthn (Passkeys) base64url codecs and PublicKeyCredential serializers (KB-P3-35, S4.2, S5.4).
 * Strict zero-library implementation relying only on native Web APIs.
 */

/**
 * Encodes an ArrayBuffer or Uint8Array into a standard base64url string (RFC 4648 Section 5).
 * Replaces '+' with '-', '/' with '_', and strips trailing '=' padding.
 */
export function bufferToBase64url(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    const b = bytes[i];
    if (b !== undefined) {
      binary += String.fromCharCode(b);
    }
  }
  const base64 = btoa(binary);
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * Decodes a base64url string into an ArrayBuffer.
 * Converts '-' to '+', '_' to '/', adds padding, and parses bytes.
 */
export function base64urlToBuffer(base64url: string): ArrayBuffer {
  let base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4 !== 0) {
    base64 += '=';
  }
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

export interface SerializedAssertionResponse {
  clientDataJSON: string;
  authenticatorData: string;
  signature: string;
  userHandle: string | null;
}

export interface SerializedAssertionCredential {
  id: string;
  rawId: string;
  type: string;
  response: SerializedAssertionResponse;
  clientExtensionResults?: Record<string, unknown> | AuthenticationExtensionsClientOutputs;
}

export interface SerializedRegistrationResponse {
  clientDataJSON: string;
  attestationObject: string;
  transports?: string[];
}

export interface SerializedRegistrationCredential {
  id: string;
  rawId: string;
  type: string;
  response: SerializedRegistrationResponse;
  clientExtensionResults?: Record<string, unknown> | AuthenticationExtensionsClientOutputs;
}

/**
 * Serializes a PublicKeyCredential returned by navigator.credentials.get() into wire JSON.
 */
export function serializeAssertionCredential(
  credential: PublicKeyCredential,
): SerializedAssertionCredential {
  const response = credential.response as AuthenticatorAssertionResponse;
  const userHandle = response.userHandle ? bufferToBase64url(response.userHandle) : null;

  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle,
    },
    clientExtensionResults:
      typeof credential.getClientExtensionResults === 'function'
        ? credential.getClientExtensionResults()
        : {},
  };
}

/**
 * Serializes a PublicKeyCredential returned by navigator.credentials.create() into wire JSON.
 */
export function serializeRegistrationCredential(
  credential: PublicKeyCredential,
): SerializedRegistrationCredential {
  const response = credential.response as AuthenticatorAttestationResponse;
  const transports = typeof response.getTransports === 'function' ? response.getTransports() : undefined;

  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
      ...(transports ? { transports } : {}),
    },
    clientExtensionResults:
      typeof credential.getClientExtensionResults === 'function'
        ? credential.getClientExtensionResults()
        : {},
  };
}

export interface PublicKeyCredentialRequestOptionsJSON {
  challenge: string;
  timeout?: number;
  rpId?: string;
  allowCredentials?: { id: string; type: string; transports?: string[] }[];
  userVerification?: UserVerificationRequirement;
}

export interface PublicKeyCredentialCreationOptionsJSON {
  rp: { name: string; id?: string };
  user: { id: string; name: string; displayName: string };
  challenge: string;
  pubKeyCredParams: { alg: number; type: string }[];
  timeout?: number;
  excludeCredentials?: { id: string; type: string; transports?: string[] }[];
  authenticatorSelection?: AuthenticatorSelectionCriteria;
  attestation?: AttestationConveyancePreference;
}

/**
 * Prepares browser PublicKeyCredentialCreationOptions from raw wire JSON.
 */
export function prepareCreationOptions(
  options: PublicKeyCredentialCreationOptionsJSON,
): PublicKeyCredentialCreationOptions {
  return {
    rp: options.rp,
    user: {
      ...options.user,
      id: base64urlToBuffer(options.user.id),
    },
    challenge: base64urlToBuffer(options.challenge),
    pubKeyCredParams: options.pubKeyCredParams.map((p) => ({
      alg: p.alg,
      type: p.type as PublicKeyCredentialType,
    })),
    timeout: options.timeout ?? 60000,
    ...(options.excludeCredentials
      ? {
          excludeCredentials: options.excludeCredentials.map((c) => ({
            id: base64urlToBuffer(c.id),
            type: c.type as PublicKeyCredentialType,
            ...(c.transports ? { transports: c.transports as AuthenticatorTransport[] } : {}),
          })),
        }
      : {}),
    ...(options.authenticatorSelection
      ? { authenticatorSelection: options.authenticatorSelection }
      : {}),
    ...(options.attestation ? { attestation: options.attestation } : {}),
  };
}

/**
 * Prepares browser PublicKeyCredentialRequestOptions from raw wire JSON.
 */
export function prepareRequestOptions(
  options: PublicKeyCredentialRequestOptionsJSON,
): PublicKeyCredentialRequestOptions {
  return {
    challenge: base64urlToBuffer(options.challenge),
    timeout: options.timeout ?? 60000,
    userVerification: options.userVerification ?? 'preferred',
    ...(options.rpId ? { rpId: options.rpId } : {}),
    ...(options.allowCredentials
      ? {
          allowCredentials: options.allowCredentials.map((c) => ({
            id: base64urlToBuffer(c.id),
            type: c.type as PublicKeyCredentialType,
            ...(c.transports ? { transports: c.transports as AuthenticatorTransport[] } : {}),
          })),
        }
      : {}),
  };
}

/**
 * Checks whether the current browser environment supports WebAuthn Passkeys.
 * Verifies window.isSecureContext, window.PublicKeyCredential, and navigator.credentials.
 */
export function isWebAuthnSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    typeof window.PublicKeyCredential !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    typeof navigator.credentials !== 'undefined' &&
    typeof navigator.credentials.create === 'function' &&
    typeof navigator.credentials.get === 'function'
  );
}
