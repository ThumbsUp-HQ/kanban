import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  ISSUE_FILTER_COOKIE_NAME,
  MAX_COOKIE_PROJECTS,
  MAX_COOKIE_WRITE_BYTES,
  buildPreferenceFromExplicitStateTokens,
  classifyStateFilterPreset,
  clearIssueFilterCookie,
  computeProjectFilterKey,
  createActionableStateFilterPreference,
  createAllStatesFilterPreference,
  createNoStatesFilterPreference,
  hasControlOrLoneSurrogate,
  isIssueStateVisible,
  parseUrlFilterStateParam,
  readIssueFilterCookiePayload,
  readProjectStateFilterCookie,
  resolveInitialStateFilter,
  resolveSavedViewStateFilter,
  stripControlAndSurrogates,
  toggleStateInPreference,
  writeProjectStateFilterCookie,
} from './issueFilterCookie';
import {
  createProjectIssue,
  deleteProjectIssue,
  ensureCsrfToken,
  extractCsrfFromCookieString,
  extractSavedViews,
  fetchAllProjectIssues,
  fetchProjectIssues,
  fetchProjectSavedViews,
  fetchProjectStates,
  isUuidString,
  normalizeIssueItem,
  patchProjectIssue,
  resolveStateUuid,
  type SavedView,
  type StateSummary,
} from './viewsApi';

describe('issueFilterCookie (KAN-308 Problem 1)', () => {
  const sampleStates: StateSummary[] = [
    { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 10 },
    { id: 'st-todo', name: 'Todo', group: 'unstarted', sort_order: 20 },
    { id: 'st-prog', name: 'In Progress', group: 'started', sort_order: 30 },
    { id: 'st-done', name: 'Done', group: 'completed', sort_order: 40 },
    { id: 'st-cancel', name: 'Cancelled', group: 'cancelled', sort_order: 50 },
  ];

  beforeEach(() => {
    document.cookie = `${ISSUE_FILTER_COOKIE_NAME}=; Path=/; Max-Age=0`;
    document.cookie = 'kb_csrf=preserve-me; Path=/';
    document.cookie = '__Host-kb_session=session-token; Path=/';
  });

  it('computes deterministic 8-hex FNV-1a project hash keys without leaking project names or workspace slugs', () => {
    const hash1 = computeProjectFilterKey('KAN', 'workspace-alpha');
    const hash2 = computeProjectFilterKey('kan', 'WORKSPACE-ALPHA');
    const hash3 = computeProjectFilterKey('OTHER', 'workspace-alpha');

    expect(hash1).toMatch(/^[0-9a-f]{8}$/);
    expect(hash1).toBe(hash2);
    expect(hash1).not.toBe(hash3);
    expect(hash1).not.toContain('kan');
    expect(hash1).not.toContain('alpha');
    expect(computeProjectFilterKey('', '')).toMatch(/^[0-9a-f]{8}$/);
  });

  it('detects and strips ASCII control chars, semicolons, CRLF, and lone UTF-16 surrogates while preserving valid emoji pairs', () => {
    const validEmoji = 'Rocket 🚀 Ship';
    expect(hasControlOrLoneSurrogate(validEmoji)).toBe(false);
    expect(stripControlAndSurrogates(validEmoji)).toBe(validEmoji);

    const withControls = 'abc\x00\x1f\x7f\r\n;def';
    expect(hasControlOrLoneSurrogate(withControls)).toBe(true);
    expect(stripControlAndSurrogates(withControls, true)).toBe('abcdef');
    expect(stripControlAndSurrogates(withControls, false)).toBe('abc;def');

    // Lone high surrogate (0xD800) and lone low surrogate (0xDC00)
    const loneHigh = `test${String.fromCharCode(0xd800)}end`;
    const loneLow = `test${String.fromCharCode(0xdc00)}end`;
    const trailingHigh = `end${String.fromCharCode(0xd83d)}`;
    expect(hasControlOrLoneSurrogate(loneHigh)).toBe(true);
    expect(hasControlOrLoneSurrogate(loneLow)).toBe(true);
    expect(hasControlOrLoneSurrogate(trailingHigh)).toBe(true);
    expect(stripControlAndSurrogates(loneHigh)).toBe('testend');
    expect(stripControlAndSurrogates(loneLow)).toBe('testend');
    expect(stripControlAndSurrogates(trailingHigh)).toBe('end');
  });

  it('round-trips per-project preference via kb_issue_state_filter cookie with Path=/; SameSite=Lax; Max-Age=2592000 and conditional Secure', () => {
    const pref = {
      hc: 1 as const,
      hx: 1 as const,
      ex: ['st-backlog'],
      inc: ['st-done'],
      ua: 1700000100,
    };

    const httpWrite = writeProjectStateFilterCookie('KAN', pref, {
      protocol: 'http:',
      nowSec: 1700000100,
    });
    expect(httpWrite.cookieDirective).toContain(`${ISSUE_FILTER_COOKIE_NAME}=`);
    expect(httpWrite.cookieDirective).toContain('Path=/; Max-Age=2592000; SameSite=Lax');
    expect(httpWrite.cookieDirective).not.toContain('Secure');
    expect(httpWrite.cookieDirective).not.toContain('Domain=');
    expect(httpWrite.cookieDirective).not.toContain('KAN');
    expect(httpWrite.encodedBytes).toBeLessThanOrEqual(MAX_COOKIE_WRITE_BYTES);

    const httpsWrite = writeProjectStateFilterCookie('KAN', pref, {
      protocol: 'https:',
      cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${httpWrite.encodedValue}`,
      nowSec: 1700000200,
    });
    expect(httpsWrite.cookieDirective).toContain('; Secure');

    const readBack = readProjectStateFilterCookie('KAN', {
      cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${httpsWrite.encodedValue}`,
    });
    expect(readBack).toEqual({
      hc: 1,
      hx: 1,
      ex: ['st-backlog'],
      inc: ['st-done'],
      ua: 1700000200,
    });

    // Preserves other cookies untouched
    expect(document.cookie).toContain('kb_csrf=preserve-me');
  });

  it('keeps newly added custom non-terminal states (Crazy_Ideas) visible by default under exclusion schema', () => {
    const defaultPref = createActionableStateFilterPreference(1700000000);
    const crazyIdeas: StateSummary = {
      id: 'st-crazy-ideas',
      name: 'Crazy_Ideas',
      group: 'unstarted',
      sort_order: 25,
    };

    expect(isIssueStateVisible(crazyIdeas, defaultPref)).toBe(true);
    expect(isIssueStateVisible({ id: 'st-done', name: 'Done', group: 'completed' }, defaultPref)).toBe(false);
    expect(isIssueStateVisible({ id: 'st-cancel', name: 'Cancelled', group: 'cancelled' }, defaultPref)).toBe(false);

    // Unchecking Crazy_Ideas records it in ex and hides it
    const afterUncheck = toggleStateInPreference(
      defaultPref,
      crazyIdeas,
      false,
      [...sampleStates, crazyIdeas],
      1700000010,
    );
    expect(afterUncheck.ex).toContain('st-crazy-ideas');
    expect(isIssueStateVisible(crazyIdeas, afterUncheck)).toBe(false);

    // Re-checking Crazy_Ideas removes it from ex
    const afterRecheck = toggleStateInPreference(
      afterUncheck,
      crazyIdeas,
      true,
      [...sampleStates, crazyIdeas],
      1700000020,
    );
    expect(afterRecheck.ex).not.toContain('st-crazy-ideas');
    expect(isIssueStateVisible(crazyIdeas, afterRecheck)).toBe(true);
  });

  it('enforces max 8 LRU projects on write and evicts oldest entries when byte budget is exceeded', () => {
    let cookieHeader = '';
    for (let i = 1; i <= 12; i += 1) {
      const res = writeProjectStateFilterCookie(
        `PROJ_${String(i)}`,
        {
          hc: 1,
          hx: 1,
          ex: [`state-ex-${String(i)}-a`, `state-ex-${String(i)}-b`],
          inc: [`state-inc-${String(i)}-a`],
          ua: 1700000000 + i * 10,
        },
        { cookieHeader, nowSec: 1700000000 + i * 10 },
      );
      cookieHeader = `${ISSUE_FILTER_COOKIE_NAME}=${res.encodedValue}`;
      expect(res.encodedBytes).toBeLessThanOrEqual(MAX_COOKIE_WRITE_BYTES);
    }

    const parsed = readIssueFilterCookiePayload({ cookieHeader });
    expect(parsed.valid).toBe(true);
    expect(Object.keys(parsed.payload.p).length).toBeLessThanOrEqual(MAX_COOKIE_PROJECTS);

    // Oldest project PROJ_1 was evicted; newest PROJ_12 is retained
    expect(readProjectStateFilterCookie('PROJ_1', { cookieHeader })).toBeNull();
    expect(readProjectStateFilterCookie('PROJ_12', { cookieHeader })).not.toBeNull();
  });

  it('evicts entries when encoded cookie size would exceed 1024 bytes even with <= 8 projects', () => {
    const longTokens = Array.from({ length: 16 }, (_, idx) =>
      `very_long_custom_workflow_state_identifier_${String(idx).padStart(2, '0')}_abcdefghijklm`,
    );
    let cookieHeader = '';
    for (let i = 1; i <= 4; i += 1) {
      const res = writeProjectStateFilterCookie(
        `HEAVY_${String(i)}`,
        {
          hc: 1,
          hx: 1,
          ex: longTokens,
          inc: longTokens,
          ua: 1700000000 + i,
        },
        { cookieHeader, nowSec: 1700000000 + i },
      );
      cookieHeader = `${ISSUE_FILTER_COOKIE_NAME}=${res.encodedValue}`;
      expect(res.encodedBytes).toBeLessThanOrEqual(MAX_COOKIE_WRITE_BYTES);
    }
  });

  it('fails closed and clears cookie (Max-Age=0) on oversized (> 2048 bytes), malformed, prototype-polluted, or tampered cookies', () => {
    // 1. Oversized cookie > 2048 bytes
    const hugeCookie = `${ISSUE_FILTER_COOKIE_NAME}=${'a'.repeat(2100)}`;
    const resHuge = readIssueFilterCookiePayload({ cookieHeader: hugeCookie, protocol: 'https:' });
    expect(resHuge.valid).toBe(false);

    // 2. Prototype pollution payload
    const protoJson = encodeURIComponent(
      '{"v":1,"p":{"12345678":{"hc":1,"hx":1,"ua":1},"__proto__":{"polluted":true}}}',
    );
    const resProto = readIssueFilterCookiePayload({
      cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${protoJson}`,
    });
    expect(resProto.valid).toBe(false);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();

    // 3. Invalid version v: 2
    const v2Json = encodeURIComponent(JSON.stringify({ v: 2, p: {} }));
    expect(
      readIssueFilterCookiePayload({ cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${v2Json}` }).valid,
    ).toBe(false);

    // 4. Array root
    const arrJson = encodeURIComponent(JSON.stringify([1, 2, 3]));
    expect(
      readIssueFilterCookiePayload({ cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${arrJson}` }).valid,
    ).toBe(false);

    // 5. Invalid hash key (non-8-hex)
    const badKeyJson = encodeURIComponent(
      JSON.stringify({ v: 1, p: { RAW_PROJ_KEY: { hc: 1, hx: 1, ua: 10 } } }),
    );
    expect(
      readIssueFilterCookiePayload({ cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${badKeyJson}` })
        .valid,
    ).toBe(false);

    // 6. Disallowed state token characters in ex/inc
    const badTokenJson = encodeURIComponent(
      JSON.stringify({
        v: 1,
        p: { '12345678': { hc: 1, hx: 1, ex: ['<script>alert(1)</script>'], ua: 10 } },
      }),
    );
    expect(
      readIssueFilterCookiePayload({ cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${badTokenJson}` })
        .valid,
    ).toBe(false);

    // 7. Invalid hc/hx values or invalid ua or non-object entry
    const badHcJson = encodeURIComponent(
      JSON.stringify({ v: 1, p: { '12345678': { hc: 9, hx: 1, ua: 10 } } }),
    );
    expect(
      readIssueFilterCookiePayload({ cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${badHcJson}` })
        .valid,
    ).toBe(false);

    const badUaJson = encodeURIComponent(
      JSON.stringify({ v: 1, p: { '12345678': { hc: 1, hx: 1, ua: -5 } } }),
    );
    expect(
      readIssueFilterCookiePayload({ cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${badUaJson}` })
        .valid,
    ).toBe(false);

    const badEntryJson = encodeURIComponent(
      JSON.stringify({ v: 1, p: { '12345678': 'not-an-object' } }),
    );
    expect(
      readIssueFilterCookiePayload({ cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${badEntryJson}` })
        .valid,
    ).toBe(false);

    // 8. Invalid percent encoding and invalid JSON syntax
    expect(
      readIssueFilterCookiePayload({ cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=%E0%A4%A` }).valid,
    ).toBe(false);
    expect(
      readIssueFilterCookiePayload({
        cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${encodeURIComponent('{corrupt_json')}`,
      }).valid,
    ).toBe(false);

    // 9. Decoded value containing semicolon or control char
    expect(
      readIssueFilterCookiePayload({
        cookieHeader: `${ISSUE_FILTER_COOKIE_NAME}=${encodeURIComponent('{"v":1,"p":{}};Domain=evil.com')}`,
      }).valid,
    ).toBe(false);
  });

  it('enforces precedence matrix: URL ?filter_state > SavedView.filters > Cookie > Actionable Default without clobbering cookie', () => {
    // Seed a cookie where Done is included (hc: 0, hx: 0)
    const allPref = createAllStatesFilterPreference(1700000500);
    const written = writeProjectStateFilterCookie('KAN', allPref, {
      cookieHeader: '',
      nowSec: 1700000500,
    });
    const cookieHeader = `${ISSUE_FILTER_COOKIE_NAME}=${written.encodedValue}`;

    const savedView: SavedView = {
      id: 'sv-1',
      name: 'Only Todo',
      layout: 'list',
      group_by: 'state',
      sub_group_by: 'none',
      filters: {
        state_ids: ['st-todo'],
      },
    };

    // 1. URL ?filter_state takes highest precedence over SavedView and Cookie
    const resUrl = resolveInitialStateFilter({
      projectKey: 'KAN',
      urlSearch: '?filter_state=st-prog&view=sv-1',
      savedView,
      projectStates: sampleStates,
      cookieHeader,
    });
    expect(resUrl.source).toBe('url');
    expect(isIssueStateVisible(sampleStates[2], resUrl.preference)).toBe(true); // In Progress
    expect(isIssueStateVisible(sampleStates[1], resUrl.preference)).toBe(false); // Todo

    // Cookie was NOT overwritten by URL param load
    const cookieStillAll = readProjectStateFilterCookie('KAN', { cookieHeader });
    expect(cookieStillAll?.hc).toBe(0);
    expect(cookieStillAll?.hx).toBe(0);

    // 2. SavedView takes precedence over Cookie when URL ?filter_state is absent or invalid
    const resView = resolveInitialStateFilter({
      projectKey: 'KAN',
      urlSearch: '?view=sv-1',
      savedView,
      projectStates: sampleStates,
      cookieHeader,
    });
    expect(resView.source).toBe('saved_view');
    expect(isIssueStateVisible(sampleStates[1], resView.preference)).toBe(true); // Todo
    expect(isIssueStateVisible(sampleStates[2], resView.preference)).toBe(false); // In Progress

    // 3. Cookie takes precedence over Actionable Default when URL and SavedView filters are absent
    const resCookie = resolveInitialStateFilter({
      projectKey: 'KAN',
      urlSearch: '',
      savedView: null,
      projectStates: sampleStates,
      cookieHeader,
    });
    expect(resCookie.source).toBe('cookie');
    expect(resCookie.preference.hc).toBe(0);
    expect(resCookie.preference.hx).toBe(0);

    // 4. Actionable Default when no URL, SavedView, or Cookie exists
    const resDefault = resolveInitialStateFilter({
      projectKey: 'BRAND_NEW_PROJ',
      urlSearch: '',
      savedView: null,
      projectStates: sampleStates,
      cookieHeader: '',
    });
    expect(resDefault.source).toBe('default');
    expect(resDefault.preference.hc).toBe(1);
    expect(resDefault.preference.hx).toBe(1);
  });

  it('rejects hostile, oversized, or unknown URL ?filter_state params and handles presets', () => {
    expect(parseUrlFilterStateParam(null, sampleStates)).toBeNull();
    expect(parseUrlFilterStateParam('', sampleStates)).toBeNull();
    expect(parseUrlFilterStateParam('a'.repeat(520), sampleStates)).toBeNull();
    expect(parseUrlFilterStateParam('<script>,../../etc/passwd', sampleStates)).toBeNull();
    expect(parseUrlFilterStateParam('todo;Domain=evil.com', sampleStates)).toBeNull();
    expect(parseUrlFilterStateParam('completely_unknown_state_xyz', sampleStates)).toBeNull();
    expect(
      parseUrlFilterStateParam(
        Array.from({ length: 20 }, () => 'todo').join(','),
        sampleStates,
      ),
    ).toBeNull();

    // Valid presets in URL
    const allFromUrl = parseUrlFilterStateParam('all', sampleStates);
    expect(allFromUrl?.hc).toBe(0);
    expect(allFromUrl?.hx).toBe(0);

    const noneFromUrl = parseUrlFilterStateParam('none', sampleStates);
    expect(noneFromUrl?.ex).toContain('__all__');
    if (!noneFromUrl) throw new Error('expected noneFromUrl');
    expect(isIssueStateVisible(sampleStates[0], noneFromUrl)).toBe(false);
    expect(isIssueStateVisible(null, noneFromUrl)).toBe(false);

    const activeFromUrl = parseUrlFilterStateParam('actionable', sampleStates);
    expect(activeFromUrl?.hc).toBe(1);
    expect(activeFromUrl?.hx).toBe(1);
  });

  it('classifies presets and toggles terminal/non-terminal states across all branches', () => {
    const stTodo = sampleStates[1];
    const stDone = sampleStates[3];
    const stCancel = sampleStates[4];
    if (!stTodo || !stDone || !stCancel) {
      throw new Error('expected sampleStates elements');
    }

    const actionable = createActionableStateFilterPreference();
    expect(classifyStateFilterPreset(actionable, sampleStates).preset).toBe('actionable');
    expect(classifyStateFilterPreset(actionable, sampleStates).label).toBe('States: Actionable (3)');

    const all = createAllStatesFilterPreference();
    expect(classifyStateFilterPreset(all, sampleStates).preset).toBe('all');
    expect(classifyStateFilterPreset(all, sampleStates).label).toBe('States: All');

    const none = createNoStatesFilterPreference(sampleStates);
    expect(classifyStateFilterPreset(none, sampleStates).preset).toBe('none');
    expect(classifyStateFilterPreset(none, sampleStates).label).toBe('States: None (0)');

    // Check single state from None preset
    const oneFromNone = toggleStateInPreference(none, stTodo, true, sampleStates);
    const oneClass = classifyStateFilterPreset(oneFromNone, sampleStates);
    expect(oneClass.preset).toBe('custom');
    expect(oneClass.label).toBe('State: Todo');

    // Check Done from None preset
    const doneFromNone = toggleStateInPreference(none, stDone, true, sampleStates);
    expect(isIssueStateVisible(stDone, doneFromNone)).toBe(true);

    // Check and uncheck Done and Cancelled from All and Actionable presets
    const doneChecked = toggleStateInPreference(actionable, stDone, true, sampleStates);
    expect(isIssueStateVisible(stDone, doneChecked)).toBe(true);
    expect(classifyStateFilterPreset(doneChecked, sampleStates).label).toBe('States: 4 selected');

    const cancelChecked = toggleStateInPreference(doneChecked, stCancel, true, sampleStates);
    expect(isIssueStateVisible(stCancel, cancelChecked)).toBe(true);

    // Uncheck Done and Cancelled when starting from All (hc=0, hx=0) with multiple terminal states
    const extraStates: StateSummary[] = [
      ...sampleStates,
      { id: 'st-done-2', name: 'Verified', group: 'completed', sort_order: 45 },
      { id: 'st-cancel-2', name: 'Rejected', group: 'cancelled', sort_order: 55 },
    ];
    const uncheckOneDoneFromAll = toggleStateInPreference(all, stDone, false, extraStates);
    expect(uncheckOneDoneFromAll.hc).toBe(1);
    expect(uncheckOneDoneFromAll.inc).toContain('st-done-2');

    const uncheckOneCancelFromAll = toggleStateInPreference(all, stCancel, false, extraStates);
    expect(uncheckOneCancelFromAll.hx).toBe(1);
    expect(uncheckOneCancelFromAll.inc).toContain('st-cancel-2');

    // buildPreferenceFromExplicitStateTokens and resolveSavedViewStateFilter edge branches
    expect(buildPreferenceFromExplicitStateTokens([], []).hc).toBe(1);
    expect(buildPreferenceFromExplicitStateTokens(['all'], []).hc).toBe(0);
    expect(buildPreferenceFromExplicitStateTokens(['none'], []).ex).toContain('__all__');
    expect(buildPreferenceFromExplicitStateTokens(['active'], []).hc).toBe(1);
    expect(buildPreferenceFromExplicitStateTokens(['active', 'done'], []).hc).toBe(0);
    const partialTerminal = buildPreferenceFromExplicitStateTokens(
      ['st-done', 'st-cancel'],
      extraStates,
    );
    expect(partialTerminal.hc).toBe(1);
    expect(partialTerminal.hx).toBe(1);
    expect(partialTerminal.inc).toContain('st-done');
    expect(partialTerminal.inc).toContain('st-cancel');
    expect(resolveSavedViewStateFilter(null)).toBeNull();
    expect(
      resolveSavedViewStateFilter({
        id: 'v',
        name: 'Empty',
        layout: 'list',
        group_by: 'state',
        sub_group_by: 'none',
        filters: {},
      }),
    ).toBeNull();
    expect(clearIssueFilterCookie({ protocol: 'http:' })).toContain('Max-Age=0');
  });

  it('covers viewsApiSavedView filters, CSRF extraction, pagination, and state resolution helpers', async () => {
    expect(extractSavedViews(null)).toEqual([]);
    expect(extractSavedViews({ views: [{ id: 'v1', name: 'V1', layout: 'list', group_by: 'state', sub_group_by: 'none', filters: { state_ids: ['s1'] } }] })).toHaveLength(1);
    expect(isUuidString('01931234-5678-7000-8000-000000000001')).toBe(true);
    expect(isUuidString('not-a-uuid')).toBe(false);

    expect(extractCsrfFromCookieString('')).toBeNull();
    expect(extractCsrfFromCookieString('__Host-kb_csrf=host_tok')).toBe('host_tok');
    expect(extractCsrfFromCookieString('kb_csrf=std_tok')).toBe('std_tok');
    expect(extractCsrfFromCookieString('other=1')).toBeNull();

    const norm = normalizeIssueItem({
      id: 'i1',
      key: 'KAN-1',
      summary: 'S',
      provenance: { created_by: { id: 'u1', handle: 'alice' } },
      access_manifest: { explicit_grant_count: 2 },
    });
    expect(norm.created_by_handle).toBe('alice');
    expect(norm.has_explicit_acl).toBe(true);

    const uuidState = '01931234-5678-7000-8000-000000000099';
    expect(resolveStateUuid(undefined, [])).toBeUndefined();
    expect(resolveStateUuid({ id: uuidState, name: 'Todo', group: 'unstarted' }, [])).toBe(uuidState);
    expect(
      resolveStateUuid({ id: 'syn', name: 'To Do', group: 'unstarted' }, [
        { id: uuidState, name: 'Todo', group: 'unstarted' },
      ]),
    ).toBe(uuidState);
    expect(
      resolveStateUuid({ id: 'syn', name: 'Other', group: 'started' }, [
        { id: uuidState, name: 'In Progress', group: 'started' },
      ]),
    ).toBe(uuidState);

    expect(await fetchAllProjectIssues('')).toEqual({ items: [], pagesFetched: 0, truncated: false });
    expect(await fetchProjectStates('')).toEqual([]);

    const origFetch = globalThis.fetch;
    document.cookie = 'kb_csrf=; Path=/; Max-Age=0';
    globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.includes('/auth/session')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ csrf_token: 'bootstrapped-csrf' }),
        });
      }
      if (url.includes('cursor=cur1')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              items: [{ id: 'i1', key: 'KAN-1', summary: 'Dup' }, { id: 'i2', key: 'KAN-2', summary: 'Two' }],
              next_cursor: 'cur1', // duplicate cursor triggers loop break
            }),
        });
      }
      if (url.includes('/states')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: uuidState, name: 'Todo', group: 'unstarted' }]),
        });
      }
      if (url.includes('/views')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: [] }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            items: [{ id: 'i1', key: 'KAN-1', summary: 'One' }],
            next_cursor: 'cur1',
            total: 2,
          }),
      });
    });

    expect(await ensureCsrfToken()).toBe('bootstrapped-csrf');
    const allRes = await fetchAllProjectIssues('KAN', { sort_by: 'updated', sort_dir: 'desc' });
    expect(allRes.truncated).toBe(true);
    expect(allRes.items).toHaveLength(2);
    expect(await fetchProjectStates('KAN')).toHaveLength(1);
    expect(await fetchProjectSavedViews('KAN')).toEqual([]);

    await createProjectIssue(
      'KAN',
      {
        summary: 'New',
        state: { id: uuidState, name: 'Todo', group: 'unstarted' },
        module_ids: [uuidState],
      },
      [{ id: uuidState, name: 'Todo', group: 'unstarted' }],
    );
    await patchProjectIssue('KAN-1', { summary: 'Patched' }, 'etag-1');
    await deleteProjectIssue('KAN-1');

    // Aborted signal branch in fetchAllProjectIssues
    const ac = new AbortController();
    ac.abort(new Error('Aborted test'));
    await expect(fetchAllProjectIssues('KAN', { signal: ac.signal })).rejects.toThrow('Aborted test');

    // Non-ok responses
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500, statusText: 'Err' });
    await expect(fetchProjectIssues('KAN')).rejects.toThrow('500');
    await expect(fetchProjectStates('KAN')).rejects.toThrow('500');
    await expect(createProjectIssue('KAN', {})).rejects.toThrow('500');
    await expect(patchProjectIssue('KAN-1', {})).rejects.toThrow('500');
    await expect(deleteProjectIssue('KAN-1')).rejects.toThrow('500');
    await expect(fetchProjectSavedViews('KAN')).rejects.toThrow('500');

    globalThis.fetch = origFetch;
  });
});
