import { useEffect } from "react";
import { downloadDoc } from "@/lib/doc";
import { useDocStore } from "@/store/useDocStore";
import { useUiStore } from "@/store/useUiStore";
import { NAV } from "@/components/shell/nav";

// Bind the app's global keyboard shortcuts:
//   ` (backtick)        toggle the command console
//   ⌘/Ctrl + S          save the project
//   ⌘/Ctrl + Z          undo (defers to native text editing while typing)
//   ⌘/Ctrl + ⇧Z / Y     redo (same deferral)
//   1-9, 0, -, p        screen nav (ignored while focused in an input)
export function useGlobalShortcuts(): void {
  useEffect(() => {
    const isTyping = (e: KeyboardEvent): boolean => {
      const el = e.target as HTMLElement | null;
      if (!el) return false;
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return true;
      if (el.isContentEditable) return true;
      return false;
    };

    const onKey = (e: KeyboardEvent) => {
      const typing = isTyping(e);

      // backtick toggles the console only when NOT typing in a field
      if (e.key === "`" && !typing) {
        e.preventDefault();
        useUiStore.getState().toggleConsole();
        return;
      }

      // ⌘/Ctrl+S — always intercept (block the browser's "save page" dialog)
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        downloadDoc(useDocStore.getState().doc);
        return;
      }

      if (typing) return; // let native editing handle Ctrl+Z etc inside fields

      // ⌘/Ctrl+Z (undo) and ⌘/Ctrl+⇧Z / Ctrl+Y (redo)
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === "z" || e.key === "Z")) {
        e.preventDefault(); useDocStore.getState().undo(); return;
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === "y" || e.key === "Y" || ((e.key === "z" || e.key === "Z") && e.shiftKey))) {
        e.preventDefault(); useDocStore.getState().redo(); return;
      }

      // Nav hotkeys (single keys, no modifiers)
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const item = NAV.find((n) => n.hot === e.key);
      if (item) useUiStore.getState().setScreen(item.id);
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
