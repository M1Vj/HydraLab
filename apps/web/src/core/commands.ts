import type { Command, QuickOpenObject } from "../lib/hydra";
import { buildCommandPaletteResults } from "../lib/hydra";

export class CommandRegistry {
  private commands = new Map<string, Command>();
  private quickOpenObjects = new Map<string, QuickOpenObject>();

  register(command: Command) {
    this.commands.set(command.id, command);
  }

  registerQuickOpen(object: QuickOpenObject) {
    this.quickOpenObjects.set(object.id, object);
  }

  get(commandId: string) {
    return this.commands.get(commandId);
  }

  run(commandId: string) {
    const command = this.commands.get(commandId);
    if (!command || command.disabledReason) return false;
    command.run();
    return true;
  }

  search(query: string) {
    return buildCommandPaletteResults([...this.commands.values()], [...this.quickOpenObjects.values()], query);
  }
}

export const commandRegistry = new CommandRegistry();
