(() => {
  let lastPlan = null;

  const el = (id) => document.getElementById(id);

  function renderPlan(data) {
    lastPlan = data && typeof data === "object" ? data : null;
    const summary = el("mqttRepairSummary");
    const list = el("mqttRepairEntities");
    const repair = el("repairMqttEntitiesButton");
    if (!summary || !list || !repair) return;

    summary.replaceChildren();
    list.replaceChildren();

    if (!lastPlan) {
      repair.disabled = true;
      return;
    }

    const fields = [
      ["Current expected", lastPlan.current_expected_count ?? 0],
      ["Current retained", lastPlan.current_retained_count ?? 0],
      ["Switch Vision retained", lastPlan.owned_retained_count ?? 0],
      ["Stale found", lastPlan.stale_count ?? 0],
    ];
    for (const [label, value] of fields) {
      const tile = document.createElement("div");
      tile.className = "diag-tile";
      const name = document.createElement("div");
      name.className = "muted";
      name.textContent = label;
      const count = document.createElement("div");
      count.className = "diag-value";
      count.textContent = String(value);
      tile.append(name, count);
      summary.appendChild(tile);
    }

    const stale = Array.isArray(lastPlan.stale_entries)
      ? lastPlan.stale_entries
      : [];
    if (stale.length) {
      const wrap = document.createElement("div");
      wrap.className = "device-card";
      const title = document.createElement("strong");
      title.textContent = "Stale Switch Vision MQTT entities";
      wrap.appendChild(title);
      const ul = document.createElement("ul");
      for (const entry of stale) {
        const li = document.createElement("li");
        li.textContent =
          entry.entity_id ||
          `${entry.component || "sensor"}.${entry.object_id || "unknown"}`;
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
      list.appendChild(wrap);
    } else {
      const clean = document.createElement("div");
      clean.className = "success";
      clean.textContent =
        "No stale Switch Vision MQTT discovery entities were found.";
      list.appendChild(clean);
    }

    repair.disabled = !(
      Number(lastPlan.stale_count) > 0 && lastPlan.plan_token
    );
  }

  async function scan() {
    const button = el("scanMqttEntitiesButton");
    const repair = el("repairMqttEntitiesButton");
    const status = el("mqttRepairStatus");
    if (!button || !repair || !status) return;

    button.disabled = true;
    repair.disabled = true;
    status.textContent =
      "Scanning retained Switch Vision MQTT discovery entries…";
    try {
      const response = await fetch(endpoint("api/maintenance/mqtt/scan"), {
        cache: "no-store",
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "MQTT maintenance scan failed");
      }
      renderPlan(data);
      status.textContent = data.stale_count
        ? `Scan complete: ${data.stale_count} stale Switch Vision MQTT ${
            data.stale_count === 1 ? "entity" : "entities"
          } found.`
        : "Scan complete: no stale Switch Vision MQTT entities found.";
    } catch (error) {
      renderPlan(null);
      status.textContent = `Could not scan MQTT entities: ${
        error.message || error
      }`;
    } finally {
      button.disabled = false;
    }
  }

  async function repair() {
    const button = el("repairMqttEntitiesButton");
    const status = el("mqttRepairStatus");
    if (!button || !status) return;

    const plan = lastPlan;
    if (
      !plan ||
      !plan.plan_token ||
      !(Number(plan.stale_count) > 0)
    ) {
      status.textContent = "Scan MQTT entities before repairing.";
      return;
    }

    const noun = plan.stale_count === 1 ? "entity" : "entities";
    if (
      !confirm(
        `Repair ${plan.stale_count} stale Switch Vision MQTT ${noun}? ` +
          "Only retained discovery entries proven to be owned by Switch Vision " +
          "SNMP2MQTT will be removed. Current generated entities and unrelated " +
          "MQTT integrations are preserved."
      )
    ) {
      return;
    }

    button.disabled = true;
    status.textContent = "Repairing stale Switch Vision MQTT entities…";
    try {
      const response = await fetch(endpoint("api/maintenance/mqtt/repair"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan_token: plan.plan_token,
          confirmation: "REPAIR STALE MQTT ENTITIES",
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "MQTT entity repair failed");
      }
      renderPlan(data);
      const warning =
        Array.isArray(data.warnings) && data.warnings.length
          ? ` Warnings: ${data.warnings.join(" | ")}`
          : "";
      const restarted = data.snmp2mqtt_restarted
        ? " SNMP2MQTT was restarted to republish the current configuration."
        : "";
      status.textContent =
        `Repair complete. Retained entries cleared: ${
          data.topics_cleared || 0
        }. Stale remaining: ${
          data.remaining_stale_count ?? data.stale_count ?? 0
        }.${restarted}${warning}`;
    } catch (error) {
      status.textContent = `Could not repair MQTT entities: ${
        error.message || error
      }`;
    } finally {
      if (lastPlan) {
        button.disabled = !(Number(lastPlan.stale_count) > 0);
      }
    }
  }

  const open = el("openMaintenanceButton");
  if (open) {
    open.addEventListener("click", () => {
      setView("maintenance");
      scan();
    });
  }
  el("scanMqttEntitiesButton")?.addEventListener("click", scan);
  el("repairMqttEntitiesButton")?.addEventListener("click", repair);

  if (
    new URLSearchParams(window.location.search).get("view") === "maintenance"
  ) {
    setView("maintenance");
    scan();
  }

  window.SwitchVisionMaintenance = { scan, repair };
})();
