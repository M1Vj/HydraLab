import React from "react";

type ModuleComponent = React.ComponentType<any>;

class ModuleRegistry {
  private registry: Map<string, ModuleComponent> = new Map();

  register(key: string, component: ModuleComponent) {
    this.registry.set(key, component);
  }

  get(key: string): ModuleComponent | undefined {
    return this.registry.get(key);
  }

  render(key: string, props: any = {}): React.ReactNode {
    const Component = this.get(key);
    if (!Component) {
      return (
        <div style={{ padding: "16px", color: "var(--fg-dim)" }}>
          Module "{key}" not registered.
        </div>
      );
    }
    return <Component {...props} />;
  }
}

export const registry = new ModuleRegistry();
