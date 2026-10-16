"""Pure add-on selector parity across Hub and MQTT maintenance."""
from unittest.mock import patch

from snmp2mqtt_addon_selector import select_snmp2mqtt_addon

sv={"slug":"abcd_switch_vision_snmp2mqtt","name":"Switch Vision SNMP2MQTT","state":"started"}
alt={"slug":"switch_vision_snmp2mqtt_addon","name":"Other SNMP2MQTT"}
other={"slug":"abc_snmp2mqtt","name":"Unknown SNMP2MQTT"}
discovery={"slug":"switch_vision_discovery_snmp2mqtt","name":"Discovery SNMP2MQTT"}
raw=[None, "garbage", {}, alt, discovery, other, sv]
for payload in ({"data":{"addons":raw}}, {"addons":raw}):
    assert select_snmp2mqtt_addon(payload) is sv
assert select_snmp2mqtt_addon({"addons":[discovery,other]}) is other
assert select_snmp2mqtt_addon({"addons":[discovery]}) is None
assert select_snmp2mqtt_addon({"addons":"not-a-list"}) is None
assert select_snmp2mqtt_addon(None) is None
tie1={"slug":"switch_vision_snmp2mqtt","name":"Equal"}
tie2={"slug":"switch_vision_snmp2mqtt","name":"Equal"}
assert select_snmp2mqtt_addon({"addons":[tie1,tie2]}) is tie1

import mqtt_maintenance_runtime as maintenance
import support_web as hub
wrapped={"data":{"addons":raw}}
with patch.object(maintenance,"_supervisor_json",return_value=wrapped) as m:
    assert maintenance._find_snmp2mqtt_addon() is sv
    m.assert_called_once_with("/addons")
with patch.object(hub,"_supervisor_json",return_value=wrapped) as h:
    assert hub._find_snmp2mqtt_addon() is sv
    h.assert_called_once_with("/addons")
print("Discovery SNMP2MQTT selector pure and dual-runtime parity: PASS")
