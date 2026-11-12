/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ENABLE_STORY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
