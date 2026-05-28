import type { Screen } from "@/store/useUiStore";

export interface NavItem {
  id: Screen;
  label: string;
  hot: string;
  icon: string;
}

// Side-nav order + keyboard hotkeys. Shared by SideNav (rendering),
// useGlobalShortcuts (binding hotkeys) and TopBar (label lookup).
export const NAV: NavItem[] = [
  { id: "fleet",     label: "ROBOT",     hot: "1", icon: "▦" },
  { id: "teleop",    label: "TELEOP",    hot: "2", icon: "✦" },
  { id: "cam",       label: "CAM",       hot: "3", icon: "⦿" },
  { id: "path",      label: "PATH",      hot: "4", icon: "↝" },
  { id: "program",   label: "PROGRAM",   hot: "p", icon: "❖" },
  { id: "import",    label: "IMPORT",    hot: "5", icon: "↓" },
  { id: "tasks",     label: "MISSIONS",  hot: "6", icon: "▶" },
  { id: "scene",     label: "SCENE 3D",  hot: "7", icon: "◈" },
  { id: "analytics", label: "ANALYTICS", hot: "8", icon: "⌬" },
  { id: "logs",      label: "LOGS",      hot: "9", icon: "≡" },
  { id: "settings",  label: "CONFIG",    hot: "0", icon: "⚙" },
];
