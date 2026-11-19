import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, rmSync, writeFileSync, readFileSync, existsSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { brotliDecompressSync, gunzipSync } from 'node:zlib';
import { shouldCompress, sriHash, precompress, runPrecompress } from './precompress';

describe('precompress build plugin', () => {
  let testDir: string;

  beforeEach(() => {
    testDir = mkdtempSync(join(tmpdir(), 'precompress-test-'));
  });

  afterEach(() => {
    if (existsSync(testDir)) {
      rmSync(testDir, { recursive: true, force: true });
    }
  });

  describe('sriHash', () => {
    it('computes expected sha384 SRI hash for abc test vector', () => {
      const input = new TextEncoder().encode('abc');
      const hash = sriHash(input);
      expect(hash).toBe(
        'sha384-ywB1P0WjXou1oD1pmsZQBycsMqsO3tFjGotgWkP/W+2AhgcroefMI1i67KE0yCWn',
      );
    });
  });

  describe('shouldCompress', () => {
    it('rejects path traversal with .. segments', () => {
      expect(shouldCompress('../etc/passwd.js', 4096)).toBe(false);
      expect(shouldCompress('assets/../../secret.js', 4096)).toBe(false);
    });

    it('rejects files smaller than 1024 bytes', () => {
      expect(shouldCompress('assets/a.js', 1023)).toBe(false);
      expect(shouldCompress('assets/a.js', 0)).toBe(false);
    });

    it('rejects files without dot extension', () => {
      expect(shouldCompress('no-extension-file', 4096)).toBe(false);
    });

    it('rejects disallowed file extensions', () => {
      expect(shouldCompress('assets/a.png', 4096)).toBe(false);
      expect(shouldCompress('assets/a.jpg', 4096)).toBe(false);
      expect(shouldCompress('assets/a.map', 4096)).toBe(false);
    });

    it('enforces 1024-byte minimum size boundary', () => {
      expect(shouldCompress('assets/a.js', 1023)).toBe(false);
      expect(shouldCompress('assets/a.js', 1024)).toBe(true);
      expect(shouldCompress('assets/a.js', 2048)).toBe(true);
    });

    it('accepts allowlisted extensions when size is sufficient', () => {
      const exts = ['.js', '.css', '.html', '.svg', '.json', '.wasm', '.txt'];
      for (const ext of exts) {
        expect(shouldCompress(`assets/bundle${ext}`, 1024)).toBe(true);
      }
    });
  });

  describe('closeBundle and runPrecompress', () => {
    it('compresses 2048-byte js file to .br and .gz and emits sri-manifest.json', async () => {
      const jsContent = Buffer.alloc(2048, 'x');
      const jsFilePath = join(testDir, 'bundle.js');
      writeFileSync(jsFilePath, jsContent);
      writeFileSync(join(testDir, 'another.js'), jsContent);

      const plugin = precompress(testDir);
      if (typeof plugin.closeBundle === 'function') {
        await plugin.closeBundle.call({} as never);
      }

      const brPath = `${jsFilePath}.br`;
      const gzPath = `${jsFilePath}.gz`;
      const manifestPath = join(testDir, 'sri-manifest.json');

      expect(existsSync(brPath)).toBe(true);
      expect(existsSync(gzPath)).toBe(true);
      expect(existsSync(manifestPath)).toBe(true);

      const brDecompressed = brotliDecompressSync(readFileSync(brPath));
      expect(brDecompressed.equals(jsContent)).toBe(true);

      const gzDecompressed = gunzipSync(readFileSync(gzPath));
      expect(gzDecompressed.equals(jsContent)).toBe(true);

      const manifestContent = JSON.parse(readFileSync(manifestPath, 'utf-8')) as Record<
        string,
        string
      >;
      expect(Object.keys(manifestContent)).toEqual(['another.js', 'bundle.js']);
      expect(manifestContent['bundle.js']).toBe(sriHash(jsContent));
      expect(manifestContent['another.js']).toBe(sriHash(jsContent));
    });

    it('skips existing .br, .gz, and sri-manifest.json on subsequent runs', () => {
      const jsContent = Buffer.alloc(2048, 'y');
      writeFileSync(join(testDir, 'app.js'), jsContent);
      writeFileSync(join(testDir, 'app.js.br'), Buffer.from('mock-br'));
      writeFileSync(join(testDir, 'app.js.gz'), Buffer.from('mock-gz'));
      writeFileSync(join(testDir, 'sri-manifest.json'), '{}');

      const manifest = runPrecompress(testDir);
      expect(Object.keys(manifest)).toEqual(['app.js']);
      expect(manifest['app.js']).toBe(sriHash(jsContent));
    });

    it('handles nested directories and skips non-compressible small files', () => {
      const subDir = join(testDir, 'assets');
      mkdirSync(subDir, { recursive: true });

      const smallCss = Buffer.from('body { margin: 0; }');
      writeFileSync(join(subDir, 'small.css'), smallCss);

      const manifest = runPrecompress(testDir);

      expect(manifest['assets/small.css']).toBe(sriHash(smallCss));
      expect(existsSync(join(subDir, 'small.css.br'))).toBe(false);
      expect(existsSync(join(subDir, 'small.css.gz'))).toBe(false);
    });

    it('resolves outDir from Vite config in configResolved hook', async () => {
      const plugin = precompress();
      if (typeof plugin.configResolved === 'function') {
        await plugin.configResolved.call({} as never, {
          build: { outDir: testDir },
        } as never);
      }

      const testFile = join(testDir, 'index.html');
      const testContent = Buffer.alloc(1500, 'a');
      writeFileSync(testFile, testContent);

      if (typeof plugin.closeBundle === 'function') {
        await plugin.closeBundle.call({} as never);
      }

      expect(existsSync(`${testFile}.br`)).toBe(true);
      expect(existsSync(`${testFile}.gz`)).toBe(true);
      expect(existsSync(join(testDir, 'sri-manifest.json'))).toBe(true);
    });

    it('defaults to dist directory if neither customDir nor configResolved sets outDir', async () => {
      const distDir = join(process.cwd(), 'dist');
      const createdDist = !existsSync(distDir);
      if (createdDist) {
        mkdirSync(distDir, { recursive: true });
      }
      try {
        const dummyFile = join(distDir, 'dummy.txt');
        writeFileSync(dummyFile, 'hello');
        const plugin = precompress();
        if (typeof plugin.closeBundle === 'function') {
          await plugin.closeBundle.call({} as never);
        }
        expect(existsSync(join(distDir, 'sri-manifest.json'))).toBe(true);
      } finally {
        if (createdDist) {
          rmSync(distDir, { recursive: true, force: true });
        }
      }
    }, 45000);
  });
});
