netmonkey
=========

Run arbitrary commands against an arbitrary list of devices, using multithreading for better performance.

**Note:** This project's main purpose was to give me a way to learn Python, netmiko, and network automation in general. The project is currently tightly coupled to my environment, is not fully implemented, and not exhaustively tested. Suggestions and contributions welcome.

## Requires

* [netmiko](https://github.com/ktbyers/netmiko) - Multi-vendor network device SSH library
* [tqdm](https://github.com/tqdm/tqdm) - Simple and extensible progress bars
* [orionsdk](https://github.com/solarwinds/OrionSDK) - Query SolarWinds Orion using SWQL

## Overview


#### Purpose
I wanted to take the heavy lifting (or you might say, monkey work ;) out of managing hundreds of network devices. Much of what netmonkey does, [NAPALM](https://github.com/napalm-automation/napalm) can do better. However, netmonkey is intentionally lightweight, lending itself well to basic one-off operations.

I work in K12 on disparate campus networks, so large-scale automation is mostly out of the question. This makes toolchains like NAPALM and Ansible a bit unwieldy, although I fully intend to learn and use them as much as possible.


#### Limitations

As a pet project, this comes with some fine print for now:

* **Tightly coupled to Cisco IOS.** We are a 99% Cisco shop, so I didn't abstract the code on my first run. Since netmiko supports many vendors, this will be easy to change.
* **Not extensively tested.** Don't expect miracles, use at your own risk.
* **Assumes SolarWinds Orion.** Uses SWQL to query Orion for devices based on custom properties for my environment. Have a look at the `get_devices()` method for info on how to set it up, and how you might adapt it to your environment.

#### Conventions

* Wherever the keyword or variable `host` is used in the source, this refers to any routable identifier for a device: IP address, hostname, or FQDN.
* All functions accept single hostnames (strings), lists, or custom SWQL queries for host targets

## Usage

#### Retrieve device info
`netmonkey.show()` accepts two paramters: the `show` command to run, and device(s) to run against. The method automatically prepends "show " to the command, so `show ip int br` would be called as `netmonkey.show('ip int br', 'rtr1')`
```py
>>> import netmonkey
>>> print netmonkey.show('snmp location', ['rtr01', 'sw02'])
Network username [adecoup]:
Network password:
Telnet password:
Enable secret:
Progress: 100%|##########################################| 2/2 [00:06<00:00,  2.00Device/s]
[{'rtr01': {'status': 0, 'message': u'MDF', 'port': 22}}, {'sw02': {'status': 0, 'message': u'Room 615a', 'port': 22}}]
>>>
```

#### Retrieve devices from SolarWinds
```py
netmonkey.get_devices(name="sw*") # Retrieves all devices with hostnames beginning with 'sw'
```

#### Combine the two

```py
>>> print netmonkey.show('snmp location', netmonkey.get_devices(name="sw*"))
Orion username [austind]:
Orion password:
Network username [austind]:
Network password:
Telnet password:    # Don't ask. Just, dont.
Enable secret:
Progress: 100%|###########################################################################| 7/7 [00:06<00:00, 13.97Device/s]
[{u'sw01': {'status': 0, 'message': u'Room 9 (IDF3)', 'port': 22}}, {u'sw02': {'status': 0, 'message': u'MDF1A', 'port': 22}}, {u'sw03': {'status': 0, 'message': u'MDF', 'port': 22}}, {u'sw04': {'status': 0, 'message': u'MDF 1B', 'port': 22}}, {u'sw05': {'status': 0, 'message': u'Room 16 (IDF2)', 'port': 22}}, {u'sw06': {'status': 0, 'message': u'Gym Closet West (IDF1)', 'port': 22}}, {u'sw07': {'status': 0, 'message': u'MDF 1C', 'port': 22}}]
```
