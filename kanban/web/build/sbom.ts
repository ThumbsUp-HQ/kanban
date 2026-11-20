import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import type { Plugin } from 'vite';

export interface WebSbomComponent {
  readonly name: string;
  readonly version: string;
  readonly ecosystem: 'node';
  readonly purl: string;
  readonly license: string;
  readonly license_verdict: 'ALLOW' | 'DENY' | 'UNKNOWN' | 'ALLOWLISTED';
  readonly scope: 'required' | 'optional' | 'dev';
  readonly description?: string;
}

export interface WebSbomManifest {
  readonly bomFormat: 'CycloneDX';
  readonly specVersion: '1.5';
  readonly components: readonly WebSbomComponent[];
}

const PERMISSIVE_LICENSES = new Set<string>([
  'MIT',
  'MIT-0',
  'ISC',
  'BSD',
  'BSD-2-Clause',
  'BSD-3-Clause',
  '0BSD',
  'Apache-2.0',
  'PSF-2.0',
  'Python-2.0',
  'PostgreSQL',
  'Zlib',
  'Unlicense',
  'CC0-1.0',
  'BlueOak-1.0.0',
  'MPL-2.0',
]);

const NORMALIZED_LICENSES: Record<string, string> = {
  'apache-2.0': 'Apache-2.0',
  'apache 2.0': 'Apache-2.0',
  'apache license 2.0': 'Apache-2.0',
  'mit': 'MIT',
  'mit license': 'MIT',
  'isc': 'ISC',
  'bsd-2-clause': 'BSD-2-Clause',
  'bsd-3-clause': 'BSD-3-Clause',
  '0bsd': '0BSD',
  'mpl-2.0': 'MPL-2.0',
  'unlicense': 'Unlicense',
  'cc0-1.0': 'CC0-1.0',
};

export function formatNpmPurl(name: string, version: string): string {
  if (name.startsWith('@') && name.includes('/')) {
    const parts = name.split('/');
    const scope = parts[0];
    const pkg = parts[1];
    if (scope && pkg) {
      return `pkg:npm/%40${scope.slice(1)}/${pkg}@${version}`;
    }
  }
  return `pkg:npm/${name}@${version}`;
}

export function classifyWebLicense(rawLicense: string): 'ALLOW' | 'DENY' | 'UNKNOWN' {
  const cleaned = rawLicense.trim().replace(/[()]/g, '');
  if (!cleaned || cleaned.toUpperCase() === 'UNKNOWN') {
    return 'UNKNOWN';
  }

  if (cleaned.includes(' OR ')) {
    const parts = cleaned.split(' OR ').map((p) => classifyWebLicense(p));
    if (parts.includes('ALLOW')) {
      return 'ALLOW';
    }
    if (parts.includes('DENY')) {
      return 'DENY';
    }
    return 'UNKNOWN';
  }

  const lowered = cleaned.toLowerCase();
  const normalized = NORMALIZED_LICENSES[lowered] ?? cleaned;
  if (PERMISSIVE_LICENSES.has(normalized)) {
    return 'ALLOW';
  }

  const upper = normalized.toUpperCase();
  if (
    upper.startsWith('GPL') ||
    upper.startsWith('AGPL') ||
    upper.startsWith('SSPL') ||
    upper.startsWith('LGPL')
  ) {
    return 'DENY';
  }

  return 'UNKNOWN';
}

export function generateWebSbom(webDir: string, outDir?: string): WebSbomManifest {
  const pkgPath = join(webDir, 'package.json');
  if (!existsSync(pkgPath)) {
    return { bomFormat: 'CycloneDX', specVersion: '1.5', components: [] };
  }

  const pkgJson = JSON.parse(readFileSync(pkgPath, 'utf8')) as {
    dependencies?: Record<string, string>;
    devDependencies?: Record<string, string>;
  };

  const nodeModulesDir = join(webDir, 'node_modules');
  const rootNodeModulesDir = join(webDir, '../../node_modules');

  const components: WebSbomComponent[] = [];

  const processPkg = (name: string, specVer: string, scope: 'required' | 'dev'): void => {
    let resolvedVersion = specVer.replace(/^[\^~>=<]/, '');
    let license = 'UNKNOWN';
    let description = '';

    const candidatePaths = [
      join(nodeModulesDir, name, 'package.json'),
      join(rootNodeModulesDir, name, 'package.json'),
    ];

    for (const cand of candidatePaths) {
      if (existsSync(cand)) {
        try {
          const depPkg = JSON.parse(readFileSync(cand, 'utf8')) as {
            version?: string;
            license?: string | { type?: string };
            licenses?: ({ type?: string } | string)[] | { type?: string };
            description?: string;
          };
          if (depPkg.version) {
            resolvedVersion = depPkg.version;
          }
          if (typeof depPkg.license === 'string') {
            license = depPkg.license;
          } else if (depPkg.license && typeof depPkg.license === 'object' && depPkg.license.type) {
            license = depPkg.license.type;
          } else if (Array.isArray(depPkg.licenses)) {
            license = depPkg.licenses
              .map((l) => (typeof l === 'string' ? l : l.type ?? 'UNKNOWN'))
              .join(' OR ');
          }
          if (depPkg.description) {
            description = depPkg.description;
          }
          break;
        } catch {
          // Ignore read error and fallback
        }
      }
    }

    const verdict = classifyWebLicense(license);
    const purl = formatNpmPurl(name, resolvedVersion);

    components.push({
      name,
      version: resolvedVersion,
      ecosystem: 'node',
      purl,
      license,
      license_verdict: verdict,
      scope,
      description,
    });
  };

  if (pkgJson.dependencies) {
    for (const [name, ver] of Object.entries(pkgJson.dependencies)) {
      processPkg(name, ver, 'required');
    }
  }

  if (pkgJson.devDependencies) {
    for (const [name, ver] of Object.entries(pkgJson.devDependencies)) {
      processPkg(name, ver, 'dev');
    }
  }

  components.sort((a, b) => a.name.localeCompare(b.name));

  const manifest: WebSbomManifest = {
    bomFormat: 'CycloneDX',
    specVersion: '1.5',
    components,
  };

  if (outDir && existsSync(outDir)) {
    const targetFile = join(outDir, 'sbom-web.json');
    writeFileSync(targetFile, JSON.stringify(manifest, null, 2) + '\n', 'utf8');
  }

  return manifest;
}

export function generateSbomWebPlugin(options?: { webDir?: string; customDir?: string }): Plugin {
  let resolvedOutDir = options?.customDir;

  return {
    name: 'kanban-sbom-web',
    apply: 'build',
    configResolved(config) {
      resolvedOutDir ??= config.build.outDir;
    },
    closeBundle() {
      const dir = resolvedOutDir ?? 'dist';
      const webDir = options?.webDir ?? process.cwd();
      generateWebSbom(webDir, dir);
    },
  };
}
