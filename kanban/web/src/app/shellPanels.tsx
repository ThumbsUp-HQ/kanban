/**
 * Shell Drawer and Modal Panel Registry (KB-P3-34, S6.3).
 * Decoupled panel invocation with accessibility announcement fallback.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useState,
  type ComponentType,
  type JSX,
  type ReactNode,
} from 'react';
import { announce } from '../api/RealtimeStatus';

export type ShellPanelComponent = ComponentType<{
  arg?: unknown;
  onClose: () => void;
}>;

const panelRegistry = new Map<string, ShellPanelComponent>();

/**
 * Registers a drawer or modal panel implementation by identifier.
 * Returns an unregister callback.
 */
export function registerShellPanel(
  id: string,
  component: ShellPanelComponent,
): () => void {
  panelRegistry.set(id, component);
  return () => {
    panelRegistry.delete(id);
  };
}

export interface ShellPanelsContextValue {
  openPanel: (id: string, arg?: unknown) => void;
  closePanel: () => void;
  activePanel: { id: string; arg?: unknown } | null;
}

const ShellPanelsContext = createContext<ShellPanelsContextValue | null>(null);

export interface ShellPanelsProviderProps {
  children: ReactNode;
}

/**
 * Context provider coordinating drawer/dialog panels hosted within the AppShell.
 */
function renderActivePanel(
  activePanel: { id: string; arg?: unknown } | null,
  closePanel: () => void,
): React.ReactNode {
  if (!activePanel) {
    return null;
  }
  const Component = panelRegistry.get(activePanel.id);
  if (!Component) {
    return null;
  }
  return <Component arg={activePanel.arg} onClose={closePanel} />;
}

export function ShellPanelsProvider({
  children,
}: ShellPanelsProviderProps): JSX.Element {
  const [activePanel, setActivePanel] = useState<{
    id: string;
    arg?: unknown;
  } | null>(null);

  const openPanel = useCallback((id: string, arg?: unknown): void => {
    const Component = panelRegistry.get(id);
    if (!Component) {
      announce('Panel not available yet');
      return;
    }
    setActivePanel({ id, arg });
  }, []);

  const closePanel = useCallback((): void => {
    setActivePanel(null);
  }, []);

  return (
    <ShellPanelsContext.Provider value={{ openPanel, closePanel, activePanel }}>
      {children}
      {renderActivePanel(activePanel, closePanel)}
    </ShellPanelsContext.Provider>
  );
}

/**
 * Accesses shell panel activation controls.
 */
export function useShellPanels(): ShellPanelsContextValue {
  const ctx = useContext(ShellPanelsContext);
  if (!ctx) {
    throw new Error('useShellPanels must be used within a ShellPanelsProvider');
  }
  return ctx;
}
