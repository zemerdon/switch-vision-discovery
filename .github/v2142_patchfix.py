from pathlib import Path

path = Path("runtime_src/discovery_job.sh")
text = path.read_text(encoding="utf-8")

dell_anchor = '''      if (model == "N2128PX-ON" && name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\\/0\\/[0-9]+$/) {
'''
inserted = '''      if (model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\\/0\\/([1-9]|[1-3][0-9]|4[0-8])$/) {
        key=name
        sub(/^FastEthernet/, "", key)
        sub(/^Fa/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " Port " (parts[3] + 0)
      }
      if (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\\/0\\/[1-4]$/) {
        key=name
        sub(/^GigabitEthernet/, "", key)
        sub(/^Gi/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " SFP 1G " (parts[3] + 0)
      }
''' + dell_anchor

# The first preparer version inserted this block at the first Dell anchor,
# outside physical_label(). Remove that misplaced copy.
if inserted in text:
    text = text.replace(inserted, dell_anchor, 1)

function_anchor = '''    function physical_label(name, idx, key, parts, member, port, label) {
''' + dell_anchor
function_insert = '''    function physical_label(name, idx, key, parts, member, port, label) {
      if (model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\\/0\\/([1-9]|[1-3][0-9]|4[0-8])$/) {
        key = name
        sub(/^FastEthernet/, "", key)
        sub(/^Fa/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " Port " (parts[3] + 0)
      }
      if (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\\/0\\/[1-4]$/) {
        key = name
        sub(/^GigabitEthernet/, "", key)
        sub(/^Gi/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " SFP 1G " (parts[3] + 0)
      }
''' + dell_anchor

if function_anchor in text:
    text = text.replace(function_anchor, function_insert, 1)
elif 'function physical_label' not in text or 'model == "WS-C3750-48P"' not in text:
    raise SystemExit("could not locate physical_label() for Catalyst 3750 patch")

path.write_text(text, encoding="utf-8")
