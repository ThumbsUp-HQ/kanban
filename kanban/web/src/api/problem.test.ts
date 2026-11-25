import { describe, expect, it, vi } from 'vitest';
import {
  ApiProblem,
  dispatchAal2StepUpIfRequired,
  isAal2StepUpCode,
  isMfaEnrollmentRequiredCode,
  isNotFound,
  isPreconditionFailed,
} from './problem.ts';

describe('ApiProblem', () => {
  it('parses an RFC 7807 body', () => {
    const p = new ApiProblem(409, {
      code: 'PARENT_CYCLE',
      title: 'Cycle',
      detail: 'would loop',
      instance: '/api/v1/issues/K-1',
    });
    expect(p).toBeInstanceOf(Error);
    expect(p.name).toBe('ApiProblem');
    expect(p.status).toBe(409);
    expect(p.code).toBe('PARENT_CYCLE');
    expect(p.title).toBe('Cycle');
    expect(p.detail).toBe('would loop');
    expect(p.instance).toBe('/api/v1/issues/K-1');
    expect(p.message).toBe('would loop');
  });

  it('falls back to title then a generated message', () => {
    expect(new ApiProblem(400, { title: 'Bad' }).message).toBe('Bad');
    expect(new ApiProblem(400, {}).message).toBe('API error 400 (UNKNOWN)');
  });

  it.each([undefined, null, 'text', 42, [1, 2], { code: '  ' }, { code: 7 }])(
    'maps malformed body %j to UNKNOWN',
    (body) => {
      expect(new ApiProblem(500, body).code).toBe('UNKNOWN');
    },
  );

  it('appends path: message from data.errors to error message', () => {
    const p = new ApiProblem(422, {
      code: 'VALIDATION_ERROR',
      detail: 'Validation failed',
      errors: [
        { path: 'client_id', message: 'Field required' },
        { path: ['public_config', 'issuer'], message: 'Extra fields not permitted' },
        { path: 42, message: 99 },
        { path: {}, message: 'ignored object path' },
        { path: false, message: 'ignored boolean path' },
        { path: ['items', 0, null, true], message: 'Invalid item' },
        { path: '', message: 'blank path ignored' },
        { path: 'empty_msg', message: '' },
        { path: 'invalid_m', message: {} },
        { path: ['x'], message: false },
        null,
        'string entry',
        { other: 'prop' },
      ],
    });
    expect(p.message).toBe(
      'Validation failed: client_id: Field required, public_config.issuer: Extra fields not permitted, 42: 99, items.0: Invalid item',
    );

    const emptyErrorsProblem = new ApiProblem(422, {
      detail: 'Failed',
      errors: [null, {}],
    });
    expect(emptyErrorsProblem.message).toBe('Failed');
  });

  it('classifies 404 uniformly and 412 precondition failures', () => {
    expect(isNotFound(new ApiProblem(404))).toBe(true);
    expect(isNotFound(new ApiProblem(403))).toBe(false);
    expect(isNotFound(new Error('x'))).toBe(false);
    expect(isPreconditionFailed(new ApiProblem(412))).toBe(true);
    expect(isPreconditionFailed(new ApiProblem(409))).toBe(false);
    expect(isPreconditionFailed('x')).toBe(false);
    expect(isAal2StepUpCode('AAL2_REQUIRED')).toBe(true);
    expect(isAal2StepUpCode('AAL2_STALE')).toBe(true);
    expect(isAal2StepUpCode('FORBIDDEN')).toBe(false);
    expect(isAal2StepUpCode(null)).toBe(false);

    expect(isMfaEnrollmentRequiredCode('MFA_ENROLLMENT_REQUIRED')).toBe(true);
    expect(isMfaEnrollmentRequiredCode('FORBIDDEN')).toBe(false);
    expect(isMfaEnrollmentRequiredCode(null)).toBe(false);
    expect(isMfaEnrollmentRequiredCode(undefined)).toBe(false);
    expect(isMfaEnrollmentRequiredCode(123)).toBe(false);
    expect(isMfaEnrollmentRequiredCode({ code: 'MFA_ENROLLMENT_REQUIRED' })).toBe(false);

    const spy = vi.fn();
    window.addEventListener('kb:open-aal2-stepup', spy);
    expect(dispatchAal2StepUpIfRequired(new ApiProblem(403, { code: 'AAL2_STALE' }))).toBe(true);
    expect(dispatchAal2StepUpIfRequired(new ApiProblem(403, { code: 'FORBIDDEN' }))).toBe(false);
    expect(dispatchAal2StepUpIfRequired(new Error('nope'))).toBe(false);
    expect(spy).toHaveBeenCalledTimes(1);
    window.removeEventListener('kb:open-aal2-stepup', spy);
  });
});
