export function chooseCustomerTargetDevice(
  devices,
  {
    tenantId,
    requestedComputer = null,
    requestedDeviceId = null,
    isOnline,
  },
) {
  if (!tenantId) throw new Error("TENANT_ID_REQUIRED");
  if (typeof isOnline !== "function") throw new Error("DEVICE_ONLINE_CHECK_REQUIRED");
  const authorized = (Array.isArray(devices) ? devices : []).filter((device) =>
    device
    && String(device.tenant_id || "") === String(tenantId)
    && String(device.state || "") === "ACTIVE"
    && !device.revoked_at_utc
  );

  if (requestedDeviceId) {
    const matches = authorized.filter((device) =>
      String(device.device_id || "") === String(requestedDeviceId)
    );
    if (matches.length !== 1) throw new Error("DEVICE_NOT_FOUND");
    return matches[0];
  }

  if (requestedComputer) {
    const target = String(requestedComputer).trim().toLocaleLowerCase();
    const matches = authorized.filter((device) =>
      String(device.device_name || "").trim().toLocaleLowerCase() === target
    );
    if (matches.length === 0) throw new Error("DEVICE_NOT_FOUND");
    if (matches.length > 1) throw new Error("COMPUTER_NAME_AMBIGUOUS");
    return matches[0];
  }

  const online = authorized.filter((device) => isOnline(device));
  if (online.length === 0) {
    throw new Error(authorized.length ? "DEVICE_OFFLINE" : "DEVICE_NOT_FOUND");
  }
  if (online.length > 1) throw new Error("COMPUTER_REQUIRED");
  return online[0];
}
