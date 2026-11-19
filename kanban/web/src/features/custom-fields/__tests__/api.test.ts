// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  approveFieldEscalation,
  createCustomField,
  deleteCustomField,
  executeCustomField,
  fetchFieldApprovals,
  fetchIssueCustomFields,
  fetchProjectCustomFields,
  qk,
  requestFieldApproval,
  updateCustomField,
} from '../api';
import * as indexExports from '../index';

describe('custom-fields api', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    document.cookie = '__Host-kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    document.cookie = '__Host-kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  describe('query keys (qk)', () => {
    it('generates consistent hierarchical query keys', () => {
      expect(qk.customFields.project('KAN')).toEqual(['custom-fields', 'project', 'KAN']);
      expect(qk.customFields.issue('KAN-42')).toEqual(['custom-fields', 'issue', 'KAN-42']);
      expect(qk.customFields.approvals('f-123')).toEqual(['custom-fields', 'approvals', 'f-123']);
    });
  });

  describe('CSRF handling', () => {
    it('includes X-CSRF-Token when kb_csrf cookie is present', async () => {
      document.cookie = 'kb_csrf=csrf-secret-123; path=/';
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: 'f-1' }),
      });

      await createCustomField('KAN', {
        slug: 'test-field',
        name: 'Test Field',
        tier: 'wasm',
        output_format: 'text',
        output_format_metadata: {},
        script_source: 'return 1;',
        target_scope: 'PROJECT',
        credential_mode: 'INVOKING_USER',
        egress_allowlist: [],
        is_enabled: true,
      });

      const call = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(call?.[0]).toBe('/api/v1/projects/KAN/custom-fields');
      const headers = (call?.[1]?.headers ?? {}) as Record<string, string>;
      expect(headers['X-CSRF-Token']).toBe('csrf-secret-123');
    });

    it('supports __Host-kb_csrf cookie variant', async () => {
      Object.defineProperty(document, 'cookie', {
        value: '__Host-kb_csrf=host-csrf-val',
        writable: true,
        configurable: true,
      });
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
      });

      await deleteCustomField('KAN', 'f-1');

      const call = vi.mocked(globalThis.fetch).mock.calls[0];
      expect(call?.[0]).toBe('/api/v1/projects/KAN/custom-fields/f-1');
      const headers = (call?.[1]?.headers ?? {}) as Record<string, string>;
      expect(headers['X-CSRF-Token']).toBe('host-csrf-val');
    });

    it('returns empty headers when document is undefined', async () => {
      const origDoc = globalThis.document;
      try {
        delete (globalThis as unknown as { document?: Document }).document;
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 204,
        });

        await deleteCustomField('KAN', 'f-1');

        const call = vi.mocked(globalThis.fetch).mock.calls[0];
        expect(call?.[0]).toBe('/api/v1/projects/KAN/custom-fields/f-1');
        const headers = (call?.[1]?.headers ?? {}) as Record<string, string>;
        expect(headers['X-CSRF-Token']).toBeUndefined();
      } finally {
        globalThis.document = origDoc;
      }
    });
  });

  describe('fetchProjectCustomFields', () => {
    it('returns array of definitions on success', async () => {
      const mockDefs = [{ id: 'f-1', slug: 'field-1' }];
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockDefs),
      });

      const res = await fetchProjectCustomFields('KAN');
      expect(res).toEqual(mockDefs);
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/projects/KAN/custom-fields');
    });

    it('returns empty array on 404 (anti-enumeration S3.4)', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
      });

      const res = await fetchProjectCustomFields('UNKNOWN');
      expect(res).toEqual([]);
    });

    it('throws error on other non-ok status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });

      await expect(fetchProjectCustomFields('KAN')).rejects.toThrow(
        'Failed to fetch custom fields: 500',
      );
    });
  });

  describe('fetchIssueCustomFields', () => {
    it('returns array of execution results on success', async () => {
      const mockResults = [{ field_id: 'f-1', value: 42 }];
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResults),
      });

      const res = await fetchIssueCustomFields('KAN-10');
      expect(res).toEqual(mockResults);
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/issues/KAN-10/custom-fields');
    });

    it('returns empty array on 404', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
      });

      const res = await fetchIssueCustomFields('KAN-999');
      expect(res).toEqual([]);
    });

    it('throws error on server failure', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
      });

      await expect(fetchIssueCustomFields('KAN-10')).rejects.toThrow(
        'Failed to fetch issue custom fields: 502',
      );
    });
  });

  describe('executeCustomField', () => {
    it('executes custom field and returns updated result', async () => {
      const mockResult = { field_id: 'f-1', status: 'SUCCESS', value: 'Active' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResult),
      });

      const res = await executeCustomField('KAN-10', 'f-1');
      expect(res).toEqual(mockResult);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/issues/KAN-10/custom-fields/f-1/execute',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('extracts error code and status on execution error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ code: 'SCRIPT_TIMEOUT', detail: 'Script timed out' }),
      });

      try {
        await executeCustomField('KAN-10', 'f-1');
        expect.unreachable('Should have thrown');
      } catch (err: unknown) {
        const error = err as { message: string; status: number; code: string };
        expect(error.message).toBe('SCRIPT_TIMEOUT');
        expect(error.status).toBe(400);
        expect(error.code).toBe('SCRIPT_TIMEOUT');
      }
    });

    it('handles non-JSON error response gracefully', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error('HTML error page')),
      });

      await expect(executeCustomField('KAN-10', 'f-1')).rejects.toThrow(
        'Execution failed with status 500',
      );
    });
  });

  describe('createCustomField', () => {
    it('posts definition and returns created object', async () => {
      const payload = {
        slug: 'status-check',
        name: 'Status Check',
        tier: 'wasm' as const,
        output_format: 'text' as const,
        output_format_metadata: {},
        script_source: 'return "ok";',
        target_scope: 'PROJECT' as const,
        credential_mode: 'INVOKING_USER' as const,
        egress_allowlist: [],
        is_enabled: true,
      };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: 'f-created', ...payload }),
      });

      const res = await createCustomField('KAN', payload);
      expect(res.id).toBe('f-created');
    });

    it('attaches detail and code on error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: () =>
          Promise.resolve({ code: 'VALIDATION_ERROR', detail: 'Slug already taken' }),
      });

      try {
        await createCustomField('KAN', {
          slug: 'existing',
          name: 'Existing',
          tier: 'wasm',
          output_format: 'text',
          output_format_metadata: {},
          script_source: 'return 1;',
          target_scope: 'PROJECT',
          credential_mode: 'INVOKING_USER',
          egress_allowlist: [],
          is_enabled: true,
        });
        expect.unreachable('Should have thrown');
      } catch (err: unknown) {
        const error = err as { message: string; status: number; code: string };
        expect(error.message).toBe('Slug already taken');
        expect(error.status).toBe(422);
        expect(error.code).toBe('VALIDATION_ERROR');
      }

      // Fallback message when detail is missing
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: () => Promise.resolve({}),
      });

      await expect(
        createCustomField('KAN', {
          slug: 'test',
          name: 'Test',
          tier: 'wasm',
          output_format: 'text',
          output_format_metadata: {},
          script_source: 'return 1;',
          target_scope: 'PROJECT',
          credential_mode: 'INVOKING_USER',
          egress_allowlist: [],
          is_enabled: true,
        }),
      ).rejects.toThrow('Create failed with status 400');
    });
  });

  describe('updateCustomField', () => {
    it('patches custom field definition', async () => {
      const update = { name: 'Renamed Field' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: 'f-1', name: 'Renamed Field' }),
      });

      const res = await updateCustomField('KAN', 'f-1', update);
      expect(res.name).toBe('Renamed Field');
    });

    it('attaches error details on update error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ code: 'INVALID_METADATA', detail: 'Invalid JSON metadata' }),
      });

      try {
        await updateCustomField('KAN', 'f-1', { name: 'Bad' });
        expect.unreachable('Should have thrown');
      } catch (err: unknown) {
        const error = err as { message: string; status: number; code: string };
        expect(error.message).toBe('Invalid JSON metadata');
        expect(error.status).toBe(400);
      }

      // Fallback message when detail is missing
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: () => Promise.resolve({}),
      });

      await expect(updateCustomField('KAN', 'f-1', { name: 'Bad' })).rejects.toThrow(
        'Update failed with status 400',
      );
    });
  });

  describe('deleteCustomField', () => {
    it('succeeds on 204 or 200 response', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
      });

      await expect(deleteCustomField('KAN', 'f-1')).resolves.toBeUndefined();

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
      });

      await expect(deleteCustomField('KAN', 'f-1')).resolves.toBeUndefined();
    });

    it('throws on non-ok status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
      });

      await expect(deleteCustomField('KAN', 'f-1')).rejects.toThrow(
        'Delete failed with status 403',
      );
    });
  });

  describe('requestFieldApproval', () => {
    it('posts escalation request and returns approval record', async () => {
      const mockApproval = { id: 'appr-1', status: 'PENDING' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockApproval),
      });

      const res = await requestFieldApproval('f-1', {
        manifest_sha256: 'sha-val',
        justification: 'Production monitoring needed',
      });
      expect(res).toEqual(mockApproval);
    });

    it('attaches code and status on error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ code: 'INVALID_MANIFEST', detail: 'Manifest sha invalid' }),
      });

      try {
        await requestFieldApproval('f-1', { manifest_sha256: 'bad', justification: 'test' });
        expect.unreachable('Should have thrown');
      } catch (err: unknown) {
        const error = err as { message: string; status: number; code: string };
        expect(error.message).toBe('Manifest sha invalid');
        expect(error.status).toBe(400);
        expect(error.code).toBe('INVALID_MANIFEST');
      }

      // Fallback message when detail is missing
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: () => Promise.resolve({}),
      });

      await expect(
        requestFieldApproval('f-1', { manifest_sha256: 'bad', justification: 'test' }),
      ).rejects.toThrow('Approval request failed with status 400');
    });
  });

  describe('approveFieldEscalation', () => {
    it('posts approval and returns approved record', async () => {
      const mockApproval = { id: 'appr-1', status: 'APPROVED' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockApproval),
      });

      const res = await approveFieldEscalation('appr-1', {
        manifest_sha256: 'sha-val',
        sp_warning_acknowledged: true,
      });
      expect(res).toEqual(mockApproval);
    });

    it('propagates 403 AAL2_REQUIRED code and status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ code: 'AAL2_REQUIRED', detail: 'Step-up required' }),
      });

      try {
        await approveFieldEscalation('appr-1', { manifest_sha256: 'sha-val' });
        expect.unreachable('Should have thrown');
      } catch (err: unknown) {
        const error = err as { message: string; status: number; code: string };
        expect(error.status).toBe(403);
        expect(error.code).toBe('AAL2_REQUIRED');
      }
    });

    it('propagates 409 MANIFEST_MISMATCH code and status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ code: 'MANIFEST_MISMATCH', detail: 'Manifest altered' }),
      });

      try {
        await approveFieldEscalation('appr-1', { manifest_sha256: 'old-sha' });
        expect.unreachable('Should have thrown');
      } catch (err: unknown) {
        const error = err as { message: string; status: number; code: string };
        expect(error.status).toBe(409);
        expect(error.code).toBe('MANIFEST_MISMATCH');
      }

      // Fallback message when detail is missing
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({}),
      });

      await expect(
        approveFieldEscalation('appr-1', { manifest_sha256: 'old-sha' }),
      ).rejects.toThrow('Approve failed with status 500');
    });
  });

  describe('fetchFieldApprovals', () => {
    it('returns array of approvals for a field', async () => {
      const mockApprovals = [{ id: 'appr-1' }];
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockApprovals),
      });

      const res = await fetchFieldApprovals('f-1');
      expect(res).toEqual(mockApprovals);
    });

    it('returns empty array on 404', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
      });

      const res = await fetchFieldApprovals('f-nonexistent');
      expect(res).toEqual([]);
    });

    it('throws on server error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });

      await expect(fetchFieldApprovals('f-1')).rejects.toThrow('Failed to fetch approvals: 500');
    });
  });

  describe('testExecuteCustomField', () => {
    it('executes draft field against issue and returns telemetry result', async () => {
      const mockResult = {
        value: 'Executed Value',
        status: 'SUCCESS',
        latency_ms: 5.2,
        logs: 'Evaluated formula',
      };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResult),
      });

      const res = await indexExports.testExecuteCustomField('KAN', {
        issue_key: 'KAN-1',
        tier: 'wasm',
        output_format: 'text',
        output_format_metadata: {},
        script_source: 'scalar: "hello"',
      });

      expect(res).toEqual(mockResult);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/projects/KAN/custom-fields/test-execute',
        expect.objectContaining({
          method: 'POST',
        }),
      );
    });

    it('throws server error message on failure', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ detail: 'Formula syntax error' }),
      });

      await expect(
        indexExports.testExecuteCustomField('KAN', {
          issue_key: 'KAN-1',
          tier: 'wasm',
          output_format: 'text',
          output_format_metadata: {},
          script_source: 'bad formula',
        }),
      ).rejects.toThrow('Formula syntax error');
    });
  });

  describe('barrel exports', () => {
    it('exports all feature components and utilities', () => {
      expect(indexExports.CustomFieldsRailSection).toBeDefined();
      expect(indexExports.CustomFieldDefinitionEditor).toBeDefined();
      expect(indexExports.CustomFieldValue).toBeDefined();
      expect(indexExports.EscalationApprovalPanel).toBeDefined();
      expect(indexExports.qk).toBeDefined();
      expect(indexExports.executeCustomField).toBeDefined();
      expect(indexExports.testExecuteCustomField).toBeDefined();
    });
  });
});
