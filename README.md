# netmonkey

## Requires

* [netmiko](https://github.com/ktbyers/netmiko) - Multi-vendor network device SSH library
* [tqdm](https://github.com/tqdm/tqdm) - Simple and extensible progress bars
* [orionsdk](https://github.com/solarwinds/OrionSDK) - Query SolarWinds Orion for devices using SWQL

## Overview

### Background

I'm a junior network engineer in the K12 space, managing ~450 Cisco devices, spanning several disparate networks that we oversee. I found out very quickly that I would hate my job if I didn't find a way to somehow automate changes. You might say I wanted to take the monkey work out of my job ;)

I signed up for @ktbyers' Python training course after finding it on /r/networking. I set up a dev environment on our Linux jumphost and tinkered with netmiko. Its power was clear to me, but all by itself, it's a bit unwieldy. I didn't want to create device objects by hand, or store credentials in plaintext, among other things.

Some other requirements I came up with:
* Detect ssh/telnet support on-the-fly (yes, I know...)
* Request credentials in a fairly secure way, storing only in memory during runtime
* Run sessions in parallel, because screenscraping IOS is *s.l.o.w.*
* Provide several ways of supplying host lists
   * Ad-hoc single host (as a string)
   * Ad-hoc multiple hosts (as a list)
   * Hosts from a plaintext file
   * Retrieved directly from our NPM (SolarWinds Orion) providing optional filters (since they have a handy API and Python module!)
* Run arbitrary show commands against any number of hosts, returning the output
* Run arbitrary one-line configuration commands against any number of hosts, returning the output
* Run custom functions that do whatever I want, parallelized against any number of hosts, with custom output (!)
* Abstract away all the junk of creating the netmiko session objects, handling exceptions, etc.

By the time I had a decent start, I looked more closely at [NAPALM](https://github.com/napalm-automation/napalm) and discovered I was basically re-implementing a very mature and robust framework, poorly. NAPALM provides a wrapper around netmiko (for IOS at least) providing some really awesome parsing methods. A NAPALM connection object gives you easy access to all kinds of info like device facts, port statistics, port info, NTP status, and more.

As it stands, the `napalm-ios` module doesn't support transport selection (for dynamically selecting telnet over ssh). Once 0.08 drops, that will become an option, and I will very likely refactor netmonkey to use NAPALM objects instead of straight netmiko objects.

### Roadmap

High on my priorities are:
* Loosely coupling everything to my environment as much as possible, hopefully making it useful to others
* Better SWQL syntax options
* Running arbitrary batches of commands from a text file (instead of only one-line commands)
* Better testing and exception handling

### Limitations

**Disclaimer:** This is a pet project in its infancy. Its main purpose is to give me a learning experience to hack away with, while also making my day job easier. Feel free to contribute or make suggestions, but don't expect miracles. You are responsible for testing, etc.

The fine print:

* **Tightly coupled to Cisco IOS.** We are a 99% Cisco shop, so I didn't abstract the code on my first run. Since netmiko supports many vendors, this will be easy to change.
* **Not extensively tested.** Don't expect miracles, use at your own risk.
* **Assumes SolarWinds Orion.** Uses SWQL to query Orion for devices based on custom properties for my environment. Have a look at the `get_devices()` method for info on how to set it up, and how you might adapt it to your environment.

### Known Issues

Most common exception types are handled gracefully, but recently I saw a random NetMikoTimeoutException when processing a large batch of hosts. The error was transient, so I couldn't dive deeper.

### Conventions

* Wherever the keyword or variable `host` is used in the source, this refers to any routable identifier for a device: IP address, hostname, or FQDN. You can use all 3 options interchangeably. Of course, hostnames and FQDNs need to resolve properly.
* All functions accept single hostnames (strings), lists, text files with one host per line, or custom SWQL queries

## Usage

### Retrieve device info
`netmonkey.show()` accepts two paramters: the `show` command to run, and device(s) to run against. The method automatically prepends "show " to the command, so `show ip int br` would be called as `netmonkey.show('ip int br', 'rtr1')`
```py
>>> import netmonkey
>>> print netmonkey.show('snmp location', ['rtr01', 'sw02'])
Network username [adecoup]:
Network password:
Telnet password:
Enable secret:
Progress: 100%|################################| 2/2 [00:06<00:00,  2.00Device/s]
[{'rtr01': {'status': 0, 'message': u'MDF', 'port': 22}}, {'sw02': {'status': 0, 'message': u'Room 615a', 'port': 22}}]
>>>
```

### Retrieve devices from SolarWinds
```py
netmonkey.get_devices(name="sw*") # Retrieves all devices with hostnames beginning with 'sw'
```

### Combine the two

```py
>>> print netmonkey.show('snmp location', netmonkey.get_devices(name="sw*"))
Orion username [austind]:
Orion password:
Network username [austind]:
Network password:
Telnet password:    # Don't ask. Just, dont.
Enable secret:
Progress: 100%|#########################################################| 7/7 [00:06<00:00, 13.97Device/s]
[{u'sw01': {'status': 0, 'message': u'Room 9 (IDF3)', 'port': 22}}, {u'sw02': {'status': 0, 'message': u'MDF1A', 'port': 22}}, {u'sw03': {'status': 0, 'message': u'MDF', 'port': 22}}, {u'sw04': {'status': 0, 'message': u'MDF 1B', 'port': 22}}, {u'sw05': {'status': 0, 'message': u'Room 16 (IDF2)', 'port': 22}}, {u'sw06': {'status': 0, 'message': u'Gym Closet West (IDF1)', 'port': 22}}, {u'sw07': {'status': 0, 'message': u'MDF 1C', 'port': 22}}]
```
