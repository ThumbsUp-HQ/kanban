import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {
  formatNpmPurl,
  classifyWebLicense,
  generateWebSbom,
  generateSbomWebPlugin,
} from '../sbom';

describe('build/sbom.ts', () => {
  it('formatNpmPurl formats unscoped, scoped, and edge-case npm packages', () => {
    expect(formatNpmPurl('react', '19.3.1')).toBe('pkg:npm/react@19.3.1');
    expect(formatNpmPurl('@tanstack/react-query', '5.67.1')).toBe(
      'pkg:npm/%40tanstack/react-query@5.67.1',
    );
    expect(formatNpmPurl('@types/node', '26.6.6')).toBe(
      'pkg:npm/%40types/node@26.6.6',
    );
    // Edge case: malformed scoped name with empty package part
    expect(formatNpmPurl('@/', '1.0.0')).toBe('pkg:npm/@/@1.0.0');
  });

  it('classifyWebLicense handles permissive, copyleft, and compound expressions', () => {
    expect(classifyWebLicense('')).toBe('UNKNOWN');
    expect(classifyWebLicense('UNKNOWN')).toBe('UNKNOWN');

    // Permissive
    expect(classifyWebLicense('MIT')).toBe('ALLOW');
    expect(classifyWebLicense('Apache-2.0')).toBe('ALLOW');
    expect(classifyWebLicense('ISC')).toBe('ALLOW');
    expect(classifyWebLicense('BSD-3-Clause')).toBe('ALLOW');

    // Copyleft
    expect(classifyWebLicense('GPL-3.0')).toBe('DENY');
    expect(classifyWebLicense('AGPL-1.0')).toBe('DENY');
    expect(classifyWebLicense('LGPL-2.1')).toBe('DENY');

    // OR Expression
    expect(classifyWebLicense('(MPL-2.0 OR Apache-2.0)')).toBe('ALLOW');
    expect(classifyWebLicense('GPL-3.0 OR AGPL-3.0')).toBe('DENY');
    expect(classifyWebLicense('UNKNOWN-A OR UNKNOWN-B')).toBe('UNKNOWN');
  });

  it('generateWebSbom returns empty manifest when package.json missing', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-sbom-none-'));
    const manifest = generateWebSbom(tmpDir);
    expect(manifest.bomFormat).toBe('CycloneDX');
    expect(manifest.components.length).toBe(0);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('generateWebSbom reads package.json, dependencies, and writes to outDir', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-sbom-test-'));
    const outDir = path.join(tmpDir, 'dist');
    fs.mkdirSync(outDir);

    const pkgJson = {
      dependencies: {
        'mock-dep': '1.0.0',
      },
      devDependencies: {
        'mock-dev': '2.0.0',
      },
    };
    fs.writeFileSync(path.join(tmpDir, 'package.json'), JSON.stringify(pkgJson));

    const nodeModules = path.join(tmpDir, 'node_modules');
    const mockDepDir = path.join(nodeModules, 'mock-dep');
    fs.mkdirSync(mockDepDir, { recursive: true });
    fs.writeFileSync(
      path.join(mockDepDir, 'package.json'),
      JSON.stringify({
        version: '1.0.0',
        license: 'MIT',
        description: 'Mock dependency description',
      }),
    );

    const manifest = generateWebSbom(tmpDir, outDir);
    expect(manifest.components.length).toBe(2);

    const depComp = manifest.components.find((c) => c.name === 'mock-dep');
    expect(depComp).toBeDefined();
    expect(depComp?.license).toBe('MIT');
    expect(depComp?.license_verdict).toBe('ALLOW');
    expect(depComp?.scope).toBe('required');

    const devComp = manifest.components.find((c) => c.name === 'mock-dev');
    expect(devComp).toBeDefined();
    expect(devComp?.scope).toBe('dev');

    // Verify file written to outDir
    const sbomFile = path.join(outDir, 'sbom-web.json');
    expect(fs.existsSync(sbomFile)).toBe(true);

    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('generateSbomWebPlugin executes closeBundle and config hook', async () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-sbom-plugin-'));
    const distDir = path.join(tmpDir, 'dist');
    fs.mkdirSync(distDir);
    fs.writeFileSync(
      path.join(tmpDir, 'package.json'),
      JSON.stringify({ dependencies: { 'test-pkg': '1.0.0' } }),
    );

    const plugin = generateSbomWebPlugin({ webDir: tmpDir, customDir: distDir });
    expect(plugin.name).toBe('kanban-sbom-web');
    expect(plugin.apply).toBe('build');

    if (typeof plugin.configResolved === 'function') {
      await plugin.configResolved.call({} as never, { build: { outDir: distDir } } as never);
    }
    if (typeof plugin.closeBundle === 'function') {
      await plugin.closeBundle.call({} as never);
    }

    expect(fs.existsSync(path.join(distDir, 'sbom-web.json'))).toBe(true);

    // Also test default options fallback
    const defaultPlugin = generateSbomWebPlugin();
    if (typeof defaultPlugin.configResolved === 'function') {
      await defaultPlugin.configResolved.call({} as never, { build: {} } as never);
    }
    if (typeof defaultPlugin.closeBundle === 'function') {
      await defaultPlugin.closeBundle.call({} as never);
    }

    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('generateWebSbom handles object license and array licenses', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-sbom-types-'));
    const pkgJson = {
      dependencies: {
        'obj-lic-pkg': '1.0.0',
        'arr-lic-pkg': '2.0.0',
      },
    };
    fs.writeFileSync(path.join(tmpDir, 'package.json'), JSON.stringify(pkgJson));

    const nodeModules = path.join(tmpDir, 'node_modules');
    const objDir = path.join(nodeModules, 'obj-lic-pkg');
    fs.mkdirSync(objDir, { recursive: true });
    fs.writeFileSync(
      path.join(objDir, 'package.json'),
      JSON.stringify({ license: { type: 'Apache-2.0' } }),
    );

    const arrDir = path.join(nodeModules, 'arr-lic-pkg');
    fs.mkdirSync(arrDir, { recursive: true });
    fs.writeFileSync(
      path.join(arrDir, 'package.json'),
      JSON.stringify({ licenses: [{ type: 'MIT' }, {}, 'ISC'] }),
    );

    const manifest = generateWebSbom(tmpDir);
    expect(manifest.components.length).toBe(2);

    const objComp = manifest.components.find((c) => c.name === 'obj-lic-pkg');
    expect(objComp?.license).toBe('Apache-2.0');
    expect(objComp?.license_verdict).toBe('ALLOW');

    const arrComp = manifest.components.find((c) => c.name === 'arr-lic-pkg');
    expect(arrComp?.license).toBe('MIT OR UNKNOWN OR ISC');
    expect(arrComp?.license_verdict).toBe('ALLOW');

    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('generateWebSbom handles only devDependencies, unparseable packages, and untyped license objects', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-sbom-devonly-'));
    const pkgJson = {
      devDependencies: {
        'untyped-lic-pkg': '1.0.0',
        'corrupt-pkg': '2.0.0',
      },
    };
    fs.writeFileSync(path.join(tmpDir, 'package.json'), JSON.stringify(pkgJson));

    const nodeModules = path.join(tmpDir, 'node_modules');
    const untypedDir = path.join(nodeModules, 'untyped-lic-pkg');
    fs.mkdirSync(untypedDir, { recursive: true });
    fs.writeFileSync(
      path.join(untypedDir, 'package.json'),
      JSON.stringify({ license: { url: 'https://example.com/license' } }),
    );

    const corruptDir = path.join(nodeModules, 'corrupt-pkg');
    fs.mkdirSync(corruptDir, { recursive: true });
    fs.writeFileSync(path.join(corruptDir, 'package.json'), 'not valid json');

    const manifest = generateWebSbom(tmpDir);
    expect(manifest.components.length).toBe(2);

    const untypedComp = manifest.components.find((c) => c.name === 'untyped-lic-pkg');
    expect(untypedComp?.license).toBe('UNKNOWN');
    expect(untypedComp?.license_verdict).toBe('UNKNOWN');

    const corruptComp = manifest.components.find((c) => c.name === 'corrupt-pkg');
    expect(corruptComp?.license).toBe('UNKNOWN');
    expect(corruptComp?.license_verdict).toBe('UNKNOWN');

    fs.rmSync(tmpDir, { recursive: true, force: true });
  });
});
