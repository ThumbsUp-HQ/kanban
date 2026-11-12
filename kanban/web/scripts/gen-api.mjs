import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(__dirname, '..');
const openapiPath = resolve(webRoot, 'openapi.json');
const outPath = resolve(webRoot, 'src/api/schema.gen.ts');

const binPath = resolve(webRoot, 'node_modules/.bin/openapi-typescript');
if (existsSync(binPath)) {
  execFileSync(binPath, [openapiPath, '-o', outPath], {
    cwd: webRoot,
    stdio: 'inherit',
  });
} else {
  execFileSync('pnpm', ['exec', 'openapi-typescript', openapiPath, '-o', outPath], {
    cwd: webRoot,
    stdio: 'inherit',
  });
}

let content = readFileSync(outPath, 'utf8');
if (!content.startsWith('/* eslint-disable */')) {
  content = `/* eslint-disable */\n${content}`;
  writeFileSync(outPath, content, 'utf8');
}
