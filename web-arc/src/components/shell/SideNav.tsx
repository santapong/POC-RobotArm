import { useUiStore } from "@/store/useUiStore";
import { NAV } from "./nav";

// Left rail: the 12 nav buttons with icon, label, hotkey. Reads/writes the
// current screen via useUiStore.
export function SideNav() {
  const screen = useUiStore(s => s.screen);
  const setScreen = useUiStore(s => s.setScreen);
  return (
    <nav className="sidenav">
      {NAV.map(item => (
        <button
          key={item.id}
          className={"navbtn" + (screen === item.id ? " active" : "")}
          onClick={() => setScreen(item.id)}
          title={item.label}
        >
          <span className="navbtn-icon">{item.icon}</span>
          <span className="navbtn-label">{item.label}</span>
          <span className="navbtn-hot">{item.hot}</span>
        </button>
      ))}
      <div style={{ flex: 1 }} />
      <div className="navfoot">
        <div className="tag dim">NODE</div>
        <div className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>ops-1.lan</div>
        <div className="tag dim" style={{ marginTop: 6 }}>BUILD</div>
        <div className="mono" style={{ fontSize: 10, color: "var(--fg-mute)" }}>web-arc · ts</div>
      </div>
    </nav>
  );
}
