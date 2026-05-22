/**
 * About dialog — mirrors the desktop's QMessageBox.information content.
 */

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/store/ui";

export function AboutDialog() {
  const activeDialog = useUIStore((s) => s.activeDialog);
  const setDialog = useUIStore((s) => s.setDialog);

  return (
    <Dialog
      open={activeDialog === "about"}
      onOpenChange={(open) => !open && setDialog(null)}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>About POC-RobotArm Station</DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-2 text-sm">
              <p>
                <strong>POC-RobotArm Station</strong> — Phase 1 web shell.
              </p>
              <p>
                Edit a flat scene-graph (frames / robots / tools / workpieces /
                fixtures / IO), save and load it as JSON, import CAD meshes,
                and emit RAPID / KRL / URScript previews of a fixed demo
                program.
              </p>
              <p className="text-muted-foreground text-xs">
                3D viewport powered by React Three Fiber + urdf-loader.
                Backend: FastAPI + PyBullet.
              </p>
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={() => setDialog(null)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
