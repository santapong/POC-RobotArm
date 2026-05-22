/**
 * ConnectionDialog — modal for creating a new I/O connection.
 *
 * Renders a protocol selector and protocol-specific config fields. On submit
 * calls POST /api/io/connections and upserts the result into the store.
 * When the server returns IO_UNAVAILABLE the caller is notified so the host
 * can disable the create button for the session.
 *
 * Phase 4 limitation: there is no edit/PATCH endpoint. To change a
 * connection's configuration, the operator must Remove the existing connection
 * and Add a new one with the desired settings.
 */

import { useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/api/client";
import { createConnection } from "@/api/io";
import { useIoStore } from "@/store/io";
import type {
  ConnectionProtocolModel,
  ModbusTcpConfigModel,
  ModbusRtuConfigModel,
  OpcUaConfigModel,
  MqttConfigModel,
  ConnectionConfigModel,
} from "@/api/types";

interface ConnectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onIoUnavailable: () => void;
}

// ---------------------------------------------------------------------------
// Per-protocol default configs
// ---------------------------------------------------------------------------

const DEFAULT_MODBUS_TCP: ModbusTcpConfigModel = {
  protocol: "modbus_tcp",
  host: "127.0.0.1",
  port: 502,
  unit_id: 1,
  timeout_s: 3.0,
};

const DEFAULT_MODBUS_RTU: ModbusRtuConfigModel = {
  protocol: "modbus_rtu",
  device: "/dev/ttyUSB0",
  baudrate: 19200,
  parity: "N",
  stopbits: 1,
  bytesize: 8,
  unit_id: 1,
  timeout_s: 3.0,
};

const DEFAULT_OPCUA: OpcUaConfigModel = {
  protocol: "opcua",
  url: "opc.tcp://localhost:4840",
  namespace: 2,
  username: null,
  password: null,
};

const DEFAULT_MQTT: MqttConfigModel = {
  protocol: "mqtt",
  host: "127.0.0.1",
  port: 1883,
  client_id: "poc-arm",
  username: null,
  password: null,
  keepalive_s: 60,
  qos: 0,
};

function defaultConfig(protocol: ConnectionProtocolModel): ConnectionConfigModel {
  switch (protocol) {
    case "modbus_tcp":
      return { ...DEFAULT_MODBUS_TCP };
    case "modbus_rtu":
      return { ...DEFAULT_MODBUS_RTU };
    case "opcua":
      return { ...DEFAULT_OPCUA };
    case "mqtt":
      return { ...DEFAULT_MQTT };
  }
}

// ---------------------------------------------------------------------------
// Field-row helper
// ---------------------------------------------------------------------------

function FieldRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="grid grid-cols-[100px_1fr] items-center gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-protocol config editors
// ---------------------------------------------------------------------------

function ModbusTcpFields({
  config,
  onChange,
}: {
  config: ModbusTcpConfigModel;
  onChange: (c: ModbusTcpConfigModel) => void;
}): JSX.Element {
  return (
    <>
      <FieldRow label="Host">
        <Input
          className="h-7 text-xs"
          value={config.host}
          onChange={(e) => onChange({ ...config, host: e.target.value })}
        />
      </FieldRow>
      <FieldRow label="Port">
        <Input
          className="h-7 text-xs"
          type="number"
          value={config.port}
          onChange={(e) => onChange({ ...config, port: parseInt(e.target.value, 10) || 502 })}
        />
      </FieldRow>
      <FieldRow label="Unit ID">
        <Input
          className="h-7 text-xs"
          type="number"
          value={config.unit_id}
          onChange={(e) =>
            onChange({ ...config, unit_id: parseInt(e.target.value, 10) || 1 })
          }
        />
      </FieldRow>
      <FieldRow label="Timeout (s)">
        <Input
          className="h-7 text-xs"
          type="number"
          step="0.5"
          value={config.timeout_s}
          onChange={(e) => onChange({ ...config, timeout_s: parseFloat(e.target.value) || 3.0 })}
        />
      </FieldRow>
    </>
  );
}

function ModbusRtuFields({
  config,
  onChange,
}: {
  config: ModbusRtuConfigModel;
  onChange: (c: ModbusRtuConfigModel) => void;
}): JSX.Element {
  return (
    <>
      <FieldRow label="Device">
        <Input
          className="h-7 text-xs"
          value={config.device}
          onChange={(e) => onChange({ ...config, device: e.target.value })}
        />
      </FieldRow>
      <FieldRow label="Baudrate">
        <Input
          className="h-7 text-xs"
          type="number"
          value={config.baudrate}
          onChange={(e) =>
            onChange({ ...config, baudrate: parseInt(e.target.value, 10) || 19200 })
          }
        />
      </FieldRow>
      <FieldRow label="Parity">
        <Select
          value={config.parity}
          onValueChange={(v) =>
            onChange({ ...config, parity: v as ModbusRtuConfigModel["parity"] })
          }
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="N" className="text-xs">None (N)</SelectItem>
            <SelectItem value="E" className="text-xs">Even (E)</SelectItem>
            <SelectItem value="O" className="text-xs">Odd (O)</SelectItem>
          </SelectContent>
        </Select>
      </FieldRow>
      <FieldRow label="Unit ID">
        <Input
          className="h-7 text-xs"
          type="number"
          value={config.unit_id}
          onChange={(e) =>
            onChange({ ...config, unit_id: parseInt(e.target.value, 10) || 1 })
          }
        />
      </FieldRow>
      <FieldRow label="Timeout (s)">
        <Input
          className="h-7 text-xs"
          type="number"
          step="0.5"
          value={config.timeout_s}
          onChange={(e) => onChange({ ...config, timeout_s: parseFloat(e.target.value) || 3.0 })}
        />
      </FieldRow>
    </>
  );
}

function OpcUaFields({
  config,
  onChange,
}: {
  config: OpcUaConfigModel;
  onChange: (c: OpcUaConfigModel) => void;
}): JSX.Element {
  return (
    <>
      <FieldRow label="URL">
        <Input
          className="h-7 text-xs"
          value={config.url}
          onChange={(e) => onChange({ ...config, url: e.target.value })}
        />
      </FieldRow>
      <FieldRow label="Namespace">
        <Input
          className="h-7 text-xs"
          type="number"
          value={config.namespace}
          onChange={(e) =>
            onChange({ ...config, namespace: parseInt(e.target.value, 10) || 2 })
          }
        />
      </FieldRow>
      <FieldRow label="Username">
        <Input
          className="h-7 text-xs"
          placeholder="(anonymous)"
          value={config.username ?? ""}
          onChange={(e) =>
            onChange({ ...config, username: e.target.value || null })
          }
        />
      </FieldRow>
      <FieldRow label="Password">
        <Input
          className="h-7 text-xs"
          type="password"
          placeholder="(none)"
          value={config.password ?? ""}
          onChange={(e) =>
            onChange({ ...config, password: e.target.value || null })
          }
        />
      </FieldRow>
    </>
  );
}

function MqttFields({
  config,
  onChange,
}: {
  config: MqttConfigModel;
  onChange: (c: MqttConfigModel) => void;
}): JSX.Element {
  return (
    <>
      <FieldRow label="Host">
        <Input
          className="h-7 text-xs"
          value={config.host}
          onChange={(e) => onChange({ ...config, host: e.target.value })}
        />
      </FieldRow>
      <FieldRow label="Port">
        <Input
          className="h-7 text-xs"
          type="number"
          value={config.port}
          onChange={(e) => onChange({ ...config, port: parseInt(e.target.value, 10) || 1883 })}
        />
      </FieldRow>
      <FieldRow label="Client ID">
        <Input
          className="h-7 text-xs"
          value={config.client_id}
          onChange={(e) => onChange({ ...config, client_id: e.target.value })}
        />
      </FieldRow>
      <FieldRow label="QoS">
        <Select
          value={String(config.qos)}
          onValueChange={(v) =>
            onChange({ ...config, qos: parseInt(v, 10) as MqttConfigModel["qos"] })
          }
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="0" className="text-xs">0 — At most once</SelectItem>
            <SelectItem value="1" className="text-xs">1 — At least once</SelectItem>
            <SelectItem value="2" className="text-xs">2 — Exactly once</SelectItem>
          </SelectContent>
        </Select>
      </FieldRow>
      <FieldRow label="Username">
        <Input
          className="h-7 text-xs"
          placeholder="(none)"
          value={config.username ?? ""}
          onChange={(e) =>
            onChange({ ...config, username: e.target.value || null })
          }
        />
      </FieldRow>
      <FieldRow label="Password">
        <Input
          className="h-7 text-xs"
          type="password"
          placeholder="(none)"
          value={config.password ?? ""}
          onChange={(e) =>
            onChange({ ...config, password: e.target.value || null })
          }
        />
      </FieldRow>
    </>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ConnectionDialog({
  open,
  onOpenChange,
  onIoUnavailable,
}: ConnectionDialogProps): JSX.Element {
  const upsertConnection = useIoStore((s) => s.upsertConnection);
  const setSignalMap = useIoStore((s) => s.setSignalMap);

  const [name, setName] = useState("");
  const [protocol, setProtocol] = useState<ConnectionProtocolModel>("modbus_tcp");
  const [config, setConfig] = useState<ConnectionConfigModel>(defaultConfig("modbus_tcp"));
  const [busy, setBusy] = useState(false);

  function handleProtocolChange(next: ConnectionProtocolModel): void {
    setProtocol(next);
    setConfig(defaultConfig(next));
  }

  function renderConfigFields(): JSX.Element {
    switch (config.protocol) {
      case "modbus_tcp":
        return (
          <ModbusTcpFields
            config={config}
            onChange={(c) => setConfig(c)}
          />
        );
      case "modbus_rtu":
        return (
          <ModbusRtuFields
            config={config}
            onChange={(c) => setConfig(c)}
          />
        );
      case "opcua":
        return (
          <OpcUaFields
            config={config}
            onChange={(c) => setConfig(c)}
          />
        );
      case "mqtt":
        return (
          <MqttFields
            config={config}
            onChange={(c) => setConfig(c)}
          />
        );
    }
  }

  async function handleCreate(): Promise<void> {
    if (!name.trim()) {
      toast.error("Connection name is required.");
      return;
    }
    setBusy(true);
    try {
      const result = await createConnection({
        name: name.trim(),
        config,
        signals: [],
      });
      upsertConnection(result);
      setSignalMap(result.name, result.signals);
      toast.success(`Connection "${result.name}" created.`);
      onOpenChange(false);
      setName("");
      setProtocol("modbus_tcp");
      setConfig(defaultConfig("modbus_tcp"));
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
        if (err.code === "IO_UNAVAILABLE") {
          onIoUnavailable();
        }
      } else {
        toast.error(String(err));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>New I/O Connection</DialogTitle>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <FieldRow label="Name">
            <Input
              className="h-7 text-xs"
              placeholder="e.g. mb_floor"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </FieldRow>

          <FieldRow label="Protocol">
            <Select
              value={protocol}
              onValueChange={(v) =>
                handleProtocolChange(v as ConnectionProtocolModel)
              }
            >
              <SelectTrigger className="h-7 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="modbus_tcp" className="text-xs">Modbus TCP</SelectItem>
                <SelectItem value="modbus_rtu" className="text-xs">Modbus RTU</SelectItem>
                <SelectItem value="opcua" className="text-xs">OPC-UA</SelectItem>
                <SelectItem value="mqtt" className="text-xs">MQTT</SelectItem>
              </SelectContent>
            </Select>
          </FieldRow>

          {renderConfigFields()}
        </div>

        <DialogFooter>
          <Button
            size="sm"
            variant="outline"
            className="text-xs"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            className="text-xs"
            onClick={() => void handleCreate()}
            disabled={busy}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
