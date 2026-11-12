import { describe, expect, it } from 'vitest';
import { ApiProblem, isNotFound, isPreconditionFailed } from './problem.ts';

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

  it('classifies 404 uniformly and 412 precondition failures', () => {
    expect(isNotFound(new ApiProblem(404))).toBe(true);
    expect(isNotFound(new ApiProblem(403))).toBe(false);
    expect(isNotFound(new Error('x'))).toBe(false);
    expect(isPreconditionFailed(new ApiProblem(412))).toBe(true);
    expect(isPreconditionFailed(new ApiProblem(409))).toBe(false);
    expect(isPreconditionFailed('x')).toBe(false);
  });
});
