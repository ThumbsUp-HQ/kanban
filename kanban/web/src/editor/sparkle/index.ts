/**
 * Public exports for Sparkle Completion (KB-P5-08, S9.1, S9.3).
 */

export const SPARKLE_MODULE_VERSION = '1.0.0';

export {
  sparkleReducer,
  isPrintableChar,
  INITIAL_SPARKLE_STATE,
  INITIAL_SPARKLE_CONTEXT,
  type SparkleStateName,
  type SparkleContext,
  type SparkleState,
  type SparkleDoneStatus,
  type SparkleEvent,
} from './sparkleMachine';

export {
  fetchSparkle,
  getCsrfToken,
  parseSseEvents,
  DEFAULT_SPARKLE_TIMEOUT_MS,
  MAX_SPARKLE_RESPONSE_BYTES,
  type EditorSurfaceKind,
  type SparkleRequestPayload,
  type SparkleClientOptions,
  type SparkleResponse,
} from './sparkleClient';

export {
  sparklePluginKey,
  sparkleCompletionPlugin,
  createSparkleCompletionPlugin,
  acceptSparkleSuggestion,
  dismissSparkleSuggestion,
  type SparklePluginState,
  type CreateSparklePluginOptions,
  type SparklePluginMeta,
} from './SparkleCompletionPlugin';

export {
  SparkleOverlayPortal,
  type SparkleOverlayPortalProps,
} from './SparkleOverlayPortal';
