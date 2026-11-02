# OpenWrt access-point setup

This guide documents prerequisites; it does not automatically reconfigure the AP.
Use a wired management connection and preserve your working wireless configuration.

## Discover actual interfaces and radios

On the AP:

```sh
ubus call system board
iw dev
uci show wireless
command -v hostapd_cli
hostapd_cli -i YOUR_INTERFACE help
```

Record the interface name, operating frequency, UCI radio section, BSSID and
channel for each configured band. Do not assume UCI radio numbering matches
interface numbering. Regulatory domain, channel availability, width and client
capabilities must match the local deployment.

The supplied active controller includes the following testbed convention:

| Band | Interface convention |
| --- | --- |
| 2.4 GHz | `phy0.0-ap0` |
| 5 GHz | `phy0.1-ap0` |
| 6 GHz | `phy0.2-ap0` |

Set `AP1_RADIO_*_IFACE` and `AP1_RADIO_*_UCI` in `.env` to the actual mappings.
Some controller/API parsing and discovery paths still contain these interface
names and band heuristics. If your AP uses different names, adapt the
`WIFI_INTERFACES` mapping and hard-coded discovery loops in `controller.py`,
and the `detect_band` / interface fallback paths in `api.py`. Arbitrary naming
has not been validated just by changing the environment variables.

## BSS Transition Management

Check that your installed hostapd/wpad build supports BSS Transition Management
and `hostapd_cli`. Check the appropriate `wifi-iface` sections for the setting
`bss_transition='1'`. Enabling it is a configuration change and should be done
using the actual section names in your own testbed.

The historical notes suggested swapping wpad packages. Those destructive
package-removal commands are deliberately not reproduced as a generic setup
recipe: package selection depends on the AP's installed firmware and features.

A BSS-TM-capable AP does not ensure the client will accept a request or support
the destination band. Record the action result and subsequent association.

## SSH setup

The controller uses a local OpenSSH client with key/agent authentication and
known-host verification. Verify the AP fingerprint manually before collecting
data. Keep the SSH key outside the repository. The AP needs read access to
`iw`, `uci`, station counters and sysfs; steering also needs permission to send
the generated hostapd commands.

The backend API binds to loopback by default. It does not configure firewall,
TLS, authentication, SSIDs or radio channels automatically.
