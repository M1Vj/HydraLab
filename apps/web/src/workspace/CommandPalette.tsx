import { useMemo, useState } from "react";
import { Command as CommandIcon, PanelTopOpen, Search, X } from "lucide-react";
import { Command } from "cmdk";
import { Dialog as DialogPrimitive } from "radix-ui";
import type { CommandRegistry } from "./commands";
import { buildPaletteResults, quickOpenFromObjects } from "./commands";
import { panelChrome, panelIds, type PanelId } from "./panelRegistry";
import { useWorkspaceData } from "./data";

export function CommandPalette({
  open,
  registry,
  onOpenChange,
  onOpenPanel,
  onQuickOpen,
}: {
  open: boolean;
  registry: CommandRegistry;
  onOpenChange: (open: boolean) => void;
  onOpenPanel: (id: PanelId) => void;
  onQuickOpen: (type: string, id: string, title: string) => void;
}) {
  const [query, setQuery] = useState("");
  const { objects } = useWorkspaceData();
  const quickOpen = objects.data ? quickOpenFromObjects(objects.data.objects) : [];
  const results = useMemo(
    () =>
      buildPaletteResults({
        commands: registry.all(),
        panels: panelIds.map((panelId) => ({ panelId, title: panelChrome[panelId].title })),
        quickOpen,
        query,
      }),
    [query, registry, quickOpen],
  );

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" />
        <DialogPrimitive.Content className="command-dialog" aria-label="Command palette">
          <Command shouldFilter={false}>
            <div className="command-input-row">
              <Search size={16} aria-hidden />
              <Command.Input value={query} onValueChange={setQuery} placeholder="Search commands, panels, notes, sources..." autoFocus />
              <DialogPrimitive.Close className="icon-button" aria-label="Close command palette">
                <X size={14} />
              </DialogPrimitive.Close>
            </div>
            <Command.List>
              <Command.Group heading="Commands">
                {results.actions.map((action) => (
                  <Command.Item
                    key={action.id}
                    value={action.id}
                    disabled={Boolean(action.disabledReason)}
                    onSelect={() => {
                      void registry.run(action.id);
                      onOpenChange(false);
                    }}
                  >
                    <CommandIcon size={14} aria-hidden />
                    <span>{action.title}</span>
                    {action.disabledReason && <small>{action.disabledReason}</small>}
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Panels">
                {results.panels.map((panel) => (
                  <Command.Item
                    key={panel.panelId}
                    value={panel.panelId}
                    onSelect={() => {
                      onOpenPanel(panel.panelId);
                      onOpenChange(false);
                    }}
                  >
                    <PanelTopOpen size={14} aria-hidden />
                    <span>{panel.title}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Quick open">
                {results.quickOpen.map((object) => (
                  <Command.Item
                    key={`${object.type}:${object.objectId}`}
                    value={`${object.type}:${object.objectId}`}
                    onSelect={() => {
                      onQuickOpen(object.type, object.objectId, object.title);
                      onOpenChange(false);
                    }}
                  >
                    <Search size={14} aria-hidden />
                    <span>{object.title}</span>
                    <small>{object.type}</small>
                  </Command.Item>
                ))}
              </Command.Group>
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function ShortcutReference({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const shortcuts = [
    ["Command Palette", "Cmd/Ctrl+K"],
    ["Toggle bottom panel", "Cmd/Ctrl+J"],
    ["Shortcut reference", "Cmd/Ctrl+/"],
    ["Focus next panel", "F6"],
    ["Close active tab", "Cmd/Ctrl+W"],
    ["Split active editor tabset", "Cmd/Ctrl+\\"],
  ];
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" />
        <DialogPrimitive.Content className="shortcut-dialog">
          <DialogPrimitive.Title>Keyboard shortcuts</DialogPrimitive.Title>
          <div className="shortcut-list">
            {shortcuts.map(([name, key]) => (
              <div key={name}>
                <span>{name}</span>
                <kbd>{key}</kbd>
              </div>
            ))}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
