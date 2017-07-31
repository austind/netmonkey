# netmonkey

A simple Python framework for managing network devices, leveraging `netmiko` and the SolarWinds Orion API.

**Full disclosure**: This is not production-ready code. It's a toy project I started to teach myself Python, netmiko, and git, and to make my day job a bit less cumbersome. This is probably most immediately useful to someone also seeking to learn Python and network automation. If you need stable, production-ready code, have a look at `NAPALM`.

## Features

* Detect ssh/telnet support on-the-fly (yes, a few of our devices still use telnet...welcome to K12)
* Request credentials at run-time, storing only in memory (nothing stored to disk)
* Leverages `multiprocessing.Pool()` to run everything in parallel, massively speeding up operations on multiple devices, with a neat little progress bar, thanks to `tqdm`
* Provide several ways of supplying hostnames/IPs:
   * Ad-hoc single host (as a `string`, e.g. `'172.16.35.240'`)
   * Ad-hoc multiple hosts (as a `list`, e.g. `['rtr1', '10.250.2.4', 'sw02']`)
   * Hosts from a plaintext file, one hostname/IP per line
   * Retrieved directly from our NPM (SolarWinds Orion)
* Run arbitrary show commands against any number of hosts, returning the output in an object format suitable for futher parsing
* Run arbitrary one-line configuration commands against any number of hosts, returning the output
* Run custom functions that do whatever I want, parallelized against any number of hosts, with custom return codes and messages
* Abstract away all the junk of requesting credentials, creating the `netmiko` session objects, handling exceptions, etc.

## Requires

* Python 2.7 on unix-like OS (Linux, MacOS). Likely wouldn't take much work to add Windows support.
* [netmiko](https://github.com/ktbyers/netmiko) - Multi-vendor network device SSH library
* [tqdm](https://github.com/tqdm/tqdm) - Simple and extensible progress bars
* [orionsdk](https://github.com/solarwinds/OrionSDK) - Query SolarWinds Orion for devices using SWQL

## Usage

### Run a `show` command

**Worth mentioning**: SNMP is generally a faster way to get info. This is just for fun.

`netmonkey.show()` accepts two paramters: the `show` command to run, and device(s) to run against. The method automatically prepends "show " to the command, so `show ip int br` would be called as `netmonkey.show('ip int br', 'rtr1')`
```py
>>> from netmonkey import netmonkey
>>> print netmonkey.show('snmp location', ['rtr01', 'sw02'])
Network username [austind]:
Network password:
Telnet password:        # Ignore this...don't ask.
Enable secret:
Progress: 100%|################################| 2/2 [00:06<00:00,  2.00Device/s]
[{'rtr01': {'status': 0, 'message': u'MDF', 'port': 22}}, {'sw02': {'status': 0, 'message': u'Room 615a', 'port': 22}}]
>>>
```

Or use a text file to supply a list of hosts.
```
cat hosts.txt
rtr01
10.250.2.3
sw02

python2.7
>>> from netmonkey import netmonkey
>>> print netmonkey.show('snmp location', 'hosts.txt')
# output omitted
```

### Retrieve devices from SolarWinds Orion

#### Setup

1. **Install API TLS cert**. The API uses its own self-signed certificate, even if you have a valid certificate for Orion (not sure why?) See [this guide](https://github.com/solarwinds/orionsdk-python#ssl-certificate-verification) for how to set it up.
1. **Edit base-query.swql**. There is a `base-query.swql.example`, use that as a starting point. See the [official docs](https://support.solarwinds.com/Success_Center/Network_Performance_Monitor_%28NPM%29/How_to_use_SolarWinds_Query_Language_%28SWQL%29) for more info.
1. Adjust `get_devices()` as necessary. I have it set to parse specific custom attributes easily. You will need to adapt it to your environment to be useful.

#### Basic usage

```py
netmonkey.get_devices(name="sw*") # Retrieves all devices with hostnames beginning with 'sw'
```

### Combine the two

```
>>> print netmonkey.show('snmp location', netmonkey.get_devices(name="sw*"))
Orion username [austind]:
Orion password:
Network username [austind]:
Network password:
Telnet password:
Enable secret:
Progress: 100%|#########################################################| 7/7 [00:06<00:00, 13.97Device/s]
[{u'sw01': {'status': 0, 'message': u'Room 9 (IDF3)', 'port': 22}}, {u'sw02': {'status': 0, 'message': u'MDF1A', 'port': 22}}, {u'sw03': {'status': 0, 'message': u'MDF', 'port': 22}}, {u'sw04': {'status': 0, 'message': u'MDF 1B', 'port': 22}}, {u'sw05': {'status': 0, 'message': u'Room 16 (IDF2)', 'port': 22}}, {u'sw06': {'status': 0, 'message': u'Gym Closet West (IDF1)', 'port': 22}}, {u'sw07': {'status': 0, 'message': u'MDF 1C', 'port': 22}}]
```

I just pulled data from 7 devices in one line of Python in 6 seconds. Not too shabby!

Output follows a list/dictionary format to make it easier for further programmatic parsing:

```py
[
    {
        'host1' = {
            'status': 0                     # Status codes. See source of netmonkey.command() for all code meanings
            'message': "Sample output"      # Output from successful command, or error message from exception
            'port': 22                      # Port connected to (None if no connection made)
    }
]
```

### Human-readable output

Maybe you don't want to further parse the output, and you just want to see it in a human-readable format.

```
>>> results = netmonkey.show('snmp location', netmonkey.get_devices(name="sw*"))
# password prompts and progress bar omitted
>>> netmonkey.print_results(results)
sw01:22 - [0] Room 9 (IDF3)
sw02:22 - [0] MDF1A
sw03:22 - [0] MDF
sw04:22 - [0] MDF 1B
sw05:22 - [0] Room 16 (IDF2)
sw06:22 - [0] Gym Closet West (IDF1)
sw07:22 - [0] MDF 1C
```

### One-line config changes

Follow the same pattern as above for show commands, except with `netmonkey.config()` instead. This will:
* Connect to the host
* Enter enable mode
* Enter config mode
* Send config change
* Write config
* Backup config via TFTP (using in-house backup alias)
* Disconnect from the host

**WARNING:** Please review the source for `netmonkey.config()` before using this in production. I call a custom backup alias that you will need to change or add before using.

```py
>>> netmonkey.config('clock timezone PST -8 0', netmonkey.get_devices(name="sw*")) # Output omitted
```

### Custom functions

Running single show/config commands are cool and all, but what about doing some real custom work? What if you need to include some logic, applying certain values only if other values exist?

You can define your own function as if it were being run against a single `netmiko` session object, then call the function with `netmonkey.run()`, optionally pairing it with `netmonkey.get_devices()`, to run it in parallel against dozens or hundreds of hosts.

```py
from netmonkey import netmonkey

# For now, the only arguments custom methods accept is the session object.
# Adding custom arguments is coming in a future release.
def new_user(session):

    # Enter enable mode
    session.enable()

    # All of `netmiko`'s methods are available (see https://pynet.twb-tech.com/blog/automation/netmiko.html)
    users = session.send_command('show running-config | include username')

    # Only move forward if 'newuser' isn't already in the running-config
    if 'newuser' not in users:
        
        # Enter config mode
        session.config_mode()

        output = session.send_command('username newuser secret 5 $1$Z30o$.......')

        # Write changes to flash
        session.send_command('copy running-config startup-config')
        
        # Call backup alias (custom to my environment)
        session.send_command('backup')

        # Return values are a tuple of ([int]statuscode, [string]message)
        # Status codes 0-6 are reserved, use anything from 7+
        return (7, "Added user 'newuser' successfully.")
    else:
        return (0, "User 'newuser' already present in config.")

# Make a list of devices you want 'newuser' added to
devices = ['sw01', 'rtr01']

# Or like in my case, I want 'newuser' on all devices
devices = netmonkey.get_devices(name='*')

# Call our custom new_user() method, parallelizing across all hosts
results = netmonkey.run(new_user, devices)

# Print results in human-readable format, skipping devices that already have 'newuser'
netmonkey.print_results(results, 1) # 1 is the minimum status code that will be displayed (ignores 0)
```

The output will be a human-readable list of only devices that either successfully added 'newuser', or had a problem (e.g., not network-reachable, no open SSH/telnet ports, bad credentials)

### Background

I'm a junior network engineer in the K12 space, managing ~450 Cisco devices, spanning several disparate networks that we oversee. I found out very quickly that I would hate my job if I didn't find a way to somehow automate changes. You might say I wanted to take the monkey work out of my job ;)

I signed up for @ktbyers Python training course after finding it on /r/networking. I set up a dev environment on our Linux jumphost and tinkered with netmiko. Its power was clear to me, but all by itself, it's a bit unwieldy. I didn't want to create device objects by hand, or store credentials in plaintext, among other things.


By the time I had a decent start, I looked more closely at [NAPALM](https://github.com/napalm-automation/napalm) and discovered I was basically re-implementing a very mature and robust framework, poorly. NAPALM provides a wrapper around netmiko (for IOS at least) providing some really awesome parsing methods. A NAPALM connection object gives you easy access to all kinds of info like device facts, port statistics, port info, NTP status, and more.

As it stands, the `napalm-ios` module doesn't support transport selection (for dynamically selecting telnet over ssh). Once 0.08 drops, that will become an option, and I will very likely refactor netmonkey to use NAPALM objects instead of straight netmiko objects.

### Roadmap

High on my priorities are:
* Loosely coupling everything to my environment as much as possible, hopefully making it more directly useful to others
* Better SWQL syntax options
* Running arbitrary batches of commands from a text file (instead of only one-line config commands)
* Better testing and exception handling

### Limitations

**Disclaimer:** This is a pet project in its infancy. Its main purpose is to give me a learning experience to hack away with, while also making my day job easier. Feel free to contribute or make suggestions, but don't expect miracles. You are responsible for testing, etc.

* **Tightly coupled to Cisco IOS.** We are a 99% Cisco shop, so I didn't abstract the code on my first run. Since netmiko supports many vendors, this will be easy to change.
* **Not extensively tested.** Don't expect miracles, use at your own risk.
* **Assumes SolarWinds Orion.** Uses SWQL to query Orion for devices based on custom properties for my environment. Have a look at the `get_devices()` method for info on how to set it up, and how you might adapt it to your environment.

### Known Issues

Most common exception types are handled gracefully, but recently I saw a random NetMikoTimeoutException when processing a large batch of hosts. The error was transient, so I couldn't dive deeper.

### Conventions

* Wherever the keyword or variable `host` is used in the source, this refers to any routable identifier for a device: IP address, hostname, or FQDN. You can use all 3 options interchangeably. Of course, hostnames and FQDNs need to resolve properly.
* All functions accept single hostnames (strings), lists, text files with one host per line, or custom SWQL queries


