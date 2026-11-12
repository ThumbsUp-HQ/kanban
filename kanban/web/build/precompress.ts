import { createHash } from 'node:crypto';
import { brotliCompressSync, gzipSync, constants } from 'node:zlib';
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import type { Plugin } from 'vite';

const ALLOWED_EXTENSIONS = new Set<string>([
  '.js',
  '.css',
  '.html',
  '.svg',
  '.json',
  '.wasm',
  '.txt',
]);

const MIN_COMPRESS_SIZE = 1024;

/**
 * Pure helper to verify if an asset file should be compressed.
 * Rejects any path containing path traversal ('..') segments.
 */
export function shouldCompress(filePath: string, size: number): boolean {
  if (filePath.includes('..')) {
    return false;
  }
  if (size < MIN_COMPRESS_SIZE) {
    return false;
  }
  const dotIndex = filePath.lastIndexOf('.');
  if (dotIndex === -1) {
    return false;
  }
  const ext = filePath.slice(dotIndex);
  return ALLOWED_EXTENSIONS.has(ext);
}

/**
 * Pure helper to compute sha384 Subresource Integrity (SRI) hash.
 */
export function sriHash(bytes: Uint8Array): string {
  const hash = createHash('sha384').update(bytes).digest('base64');
  return `sha384-${hash}`;
}

/**
 * Recursively collects all file paths inside a directory.
 */
function collectFiles(dirPath: string): string[] {
  const results: string[] = [];
  const entries = readdirSync(dirPath, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(dirPath, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectFiles(fullPath));
    } else {
      results.push(fullPath);
    }
  }
  return results;
}

/**
 * Executes precompression and SRI manifest generation on the target directory.
 */
export function runPrecompress(outDir: string): Record<string, string> {
  const manifest: Record<string, string> = {};
  const allFiles = collectFiles(outDir);

  for (const fullPath of allFiles) {
    const relPosix = relative(outDir, fullPath).split('\\').join('/');
    if (
      relPosix.endsWith('.br') ||
      relPosix.endsWith('.gz') ||
      relPosix === 'sri-manifest.json'
    ) {
      continue;
    }

    const content = readFileSync(fullPath);
    manifest[relPosix] = sriHash(content);

    if (shouldCompress(relPosix, content.byteLength)) {
      const brBytes = brotliCompressSync(content, {
        params: {
          [constants.BROTLI_PARAM_QUALITY]: 11,
        },
      });
      writeFileSync(`${fullPath}.br`, brBytes);

      const gzBytes = gzipSync(content, {
        level: 9,
      });
      writeFileSync(`${fullPath}.gz`, gzBytes);
    }
  }

  const sortedManifest: Record<string, string> = {};
  for (const [key, value] of Object.entries(manifest).sort(([a], [b]) => a.localeCompare(b))) {
    sortedManifest[key] = value;
  }

  const manifestPath = join(outDir, 'sri-manifest.json');
  writeFileSync(manifestPath, JSON.stringify(sortedManifest, null, 2) + '\n', 'utf-8');

  return sortedManifest;
}

/**
 * Vite plugin that generates .br and .gz precompressed siblings
 * and an sri-manifest.json artifact inside the output directory.
 */
export function precompress(customDir?: string): Plugin {
  let resolvedOutDir = customDir;

  return {
    name: 'kanban-precompress',
    apply: 'build',
    configResolved(config) {
      resolvedOutDir ??= config.build.outDir;
    },
    closeBundle() {
      const dir = resolvedOutDir ?? 'dist';
      runPrecompress(dir);
    },
  };
}
