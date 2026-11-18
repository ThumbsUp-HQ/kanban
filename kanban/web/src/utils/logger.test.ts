import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  STATUS_BLOCKED,
  STATUS_ERROR,
  STATUS_OK,
  formatLogArgs,
  logBlocked,
  logError,
  logInfo,
  logOk,
  logWarn,
  logger,
  prefixLines,
} from './logger';

describe('logger utility (KANBA-224)', () => {
  beforeEach(() => {
    vi.spyOn(console, 'info').mockImplementation(vi.fn());
    vi.spyOn(console, 'warn').mockImplementation(vi.fn());
    vi.spyOn(console, 'error').mockImplementation(vi.fn());
    vi.spyOn(console, 'debug').mockImplementation(vi.fn());
    vi.spyOn(console, 'log').mockImplementation(vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('prefixLines', () => {
    it('returns icon when text is empty', () => {
      expect(prefixLines(STATUS_OK, '')).toBe('👍');
    });

    it('prefixes a single line with icon and space', () => {
      expect(prefixLines(STATUS_OK, 'System initialized')).toBe('👍 System initialized');
      expect(prefixLines(STATUS_BLOCKED, 'Rate limit approaching')).toBe('⛔ Rate limit approaching');
      expect(prefixLines(STATUS_ERROR, 'Uncaught crash')).toBe('❌ Uncaught crash');
    });

    it('prefixes every line in multi-line text', () => {
      const input = 'First line\nSecond line\nThird line';
      const expected = '👍 First line\n👍 Second line\n👍 Third line';
      expect(prefixLines(STATUS_OK, input)).toBe(expected);
    });

    it('handles CRLF line breaks and empty lines within multi-line text', () => {
      const input = 'Line A\r\n\r\nLine B';
      const expected = '👍 Line A\n👍\n👍 Line B';
      expect(prefixLines(STATUS_OK, input)).toBe(expected);
    });

    it('deduplicates leading icons if already present on lines', () => {
      const input = '👍 Already ok\n⛔ Blocked\n❌ Error';
      const result = prefixLines(STATUS_OK, input);
      expect(result).toBe('👍 Already ok\n👍 Blocked\n👍 Error');
      expect(result).not.toContain('👍 👍');
    });
  });

  describe('formatLogArgs', () => {
    it('returns array with icon when no args provided', () => {
      expect(formatLogArgs(STATUS_OK)).toEqual(['👍']);
    });

    it('formats string first argument and preserves remaining arguments', () => {
      const extraObj = { status: 200 };
      const formatted = formatLogArgs(STATUS_OK, 'User login: %s', 'alice', extraObj);
      expect(formatted).toEqual(['👍 User login: %s', 'alice', extraObj]);
    });

    it('formats Error instance using stack trace if available', () => {
      const err = new Error('Test failure');
      err.stack = 'Error: Test failure\n    at testFunction (/app/test.ts:10:5)';
      const formatted = formatLogArgs(STATUS_ERROR, err);
      expect(typeof formatted[0]).toBe('string');
      expect(formatted[0]).toContain('❌ Error: Test failure');
      expect(formatted[0]).toContain('❌ at testFunction');
    });

    it('formats Error instance using name and message if stack is empty', () => {
      const err = new Error('No stack error');
      err.stack = '';
      const formatted = formatLogArgs(STATUS_ERROR, err);
      expect(formatted[0]).toBe('❌ Error: No stack error');
    });

    it('prepends icon as first arg when first arg is not a string or Error', () => {
      const numArg = 42;
      const objArg = { id: 'item-1' };
      const formatted = formatLogArgs(STATUS_BLOCKED, numArg, objArg);
      expect(formatted).toEqual(['⛔', 42, { id: 'item-1' }]);
    });
  });

  describe('logger methods and aliases', () => {
    it('calls console.info with 👍 prefix', () => {
      logger.info('Application ready');
      expect(console.info).toHaveBeenCalledWith('👍 Application ready');
    });

    it('calls console.warn with ⛔ prefix', () => {
      logger.warn('Token expiring');
      expect(console.warn).toHaveBeenCalledWith('⛔ Token expiring');
    });

    it('calls console.error with ❌ prefix', () => {
      logger.error('Failed to sync board');
      expect(console.error).toHaveBeenCalledWith('❌ Failed to sync board');
    });

    it('calls console.debug with 👍 prefix', () => {
      logger.debug('Debug payload', { traceId: '123' });
      expect(console.debug).toHaveBeenCalledWith('👍 Debug payload', { traceId: '123' });
    });

    it('calls console.log with 👍 prefix', () => {
      logger.log('General output');
      expect(console.log).toHaveBeenCalledWith('👍 General output');
    });

    it('supports standalone alias exports', () => {
      logOk('OK message');
      expect(console.info).toHaveBeenCalledWith('👍 OK message');

      logInfo('Info message');
      expect(console.info).toHaveBeenCalledWith('👍 Info message');

      logBlocked('Blocked message');
      expect(console.warn).toHaveBeenCalledWith('⛔ Blocked message');

      logWarn('Warn message');
      expect(console.warn).toHaveBeenCalledWith('⛔ Warn message');

      logError('Error message');
      expect(console.error).toHaveBeenCalledWith('❌ Error message');
    });
  });
});
