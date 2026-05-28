// Minimal OrbitControls — drag = orbit, wheel = zoom, right-drag = pan.
// Ported from the prototype's inline implementation as a typed class so we
// don't depend on `three/examples/jsm/controls/OrbitControls` (which has
// shifted across three releases). Behavior is intentionally identical to the
// original.

import { Matrix4, type PerspectiveCamera, Spherical, Vector3 } from "three";

type State = "none" | "rotate" | "pan";

export class OrbitControls {
  object: PerspectiveCamera;
  domElement: HTMLElement;
  target = new Vector3();
  enableDamping = false;
  dampingFactor = 0.05;
  minDistance = 0.1;
  maxDistance = 50;
  minPolarAngle = 0;
  maxPolarAngle = Math.PI;
  autoRotate = false;
  autoRotateSpeed = 0.5;
  zoomSpeed = 1.0;

  private _offset = new Vector3();
  private _spherical = new Spherical();
  private _sphericalDelta = new Spherical();
  private _scale = 1;
  private _panOffset = new Vector3();
  private _state: State = "none";
  private _startX = 0;
  private _startY = 0;

  constructor(camera: PerspectiveCamera, dom: HTMLElement) {
    this.object = camera;
    this.domElement = dom;

    dom.addEventListener("pointerdown", this._onPointerDown);
    dom.addEventListener("pointermove", this._onPointerMove);
    dom.addEventListener("pointerup", this._onPointerUp);
    dom.addEventListener("pointercancel", this._onPointerUp);
    dom.addEventListener("wheel", this._onWheel, { passive: false });
    dom.addEventListener("contextmenu", this._onContextMenu);
  }

  private _zoomStep(): number { return Math.pow(0.95, this.zoomSpeed); }

  private _panLeft(distance: number, m: Matrix4): void {
    const v = new Vector3();
    v.setFromMatrixColumn(m, 0);
    v.multiplyScalar(-distance);
    this._panOffset.add(v);
  }
  private _panUp(distance: number, m: Matrix4): void {
    const v = new Vector3();
    v.setFromMatrixColumn(m, 1);
    v.multiplyScalar(distance);
    this._panOffset.add(v);
  }
  private _pan(dx: number, dy: number): void {
    const el = this.domElement;
    const off = new Vector3().copy(this.object.position).sub(this.target);
    let dist = off.length();
    dist *= Math.tan((this.object.fov / 2) * Math.PI / 180);
    this._panLeft(2 * dx * dist / el.clientHeight, this.object.matrix);
    this._panUp(2 * dy * dist / el.clientHeight, this.object.matrix);
  }

  private _onPointerDown = (e: PointerEvent): void => {
    this._state = e.button === 2 || e.button === 1 ? "pan" : "rotate";
    this._startX = e.clientX; this._startY = e.clientY;
    this.domElement.setPointerCapture(e.pointerId);
  };
  private _onPointerMove = (e: PointerEvent): void => {
    if (this._state === "none") return;
    const dx = e.clientX - this._startX;
    const dy = e.clientY - this._startY;
    this._startX = e.clientX; this._startY = e.clientY;
    if (this._state === "rotate") {
      this._sphericalDelta.theta -= 2 * Math.PI * dx / this.domElement.clientHeight;
      this._sphericalDelta.phi   -= 2 * Math.PI * dy / this.domElement.clientHeight;
    } else if (this._state === "pan") {
      this._pan(dx, dy);
    }
  };
  private _onPointerUp = (): void => { this._state = "none"; };
  private _onWheel = (e: WheelEvent): void => {
    e.preventDefault();
    if (e.deltaY < 0) this._scale /= this._zoomStep();
    else this._scale *= this._zoomStep();
  };
  private _onContextMenu = (e: MouseEvent): void => { e.preventDefault(); };

  update(): void {
    const pos = this.object.position;
    this._offset.copy(pos).sub(this.target);
    this._spherical.setFromVector3(this._offset);
    if (this.autoRotate && this._state === "none") {
      this._sphericalDelta.theta -= (2 * Math.PI / 60 / 60) * this.autoRotateSpeed * 60;
    }
    this._spherical.theta += this._sphericalDelta.theta;
    this._spherical.phi   += this._sphericalDelta.phi;
    this._spherical.phi = Math.max(this.minPolarAngle, Math.min(this.maxPolarAngle, this._spherical.phi));
    this._spherical.makeSafe();
    this._spherical.radius *= this._scale;
    this._spherical.radius = Math.max(this.minDistance, Math.min(this.maxDistance, this._spherical.radius));
    this.target.add(this._panOffset);
    this._offset.setFromSpherical(this._spherical);
    pos.copy(this.target).add(this._offset);
    this.object.lookAt(this.target);
    if (this.enableDamping) {
      this._sphericalDelta.theta *= 1 - this.dampingFactor;
      this._sphericalDelta.phi   *= 1 - this.dampingFactor;
      this._panOffset.multiplyScalar(1 - this.dampingFactor);
    } else {
      this._sphericalDelta.set(0, 0, 0);
      this._panOffset.set(0, 0, 0);
    }
    this._scale = 1;
  }

  dispose(): void {
    const d = this.domElement;
    d.removeEventListener("pointerdown", this._onPointerDown);
    d.removeEventListener("pointermove", this._onPointerMove);
    d.removeEventListener("pointerup", this._onPointerUp);
    d.removeEventListener("pointercancel", this._onPointerUp);
    d.removeEventListener("wheel", this._onWheel);
    d.removeEventListener("contextmenu", this._onContextMenu);
  }
}
