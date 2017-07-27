import os
import netmiko
import orionsdk
from getpass import (getpass, getuser)
from distutils.util import strtobool
import urllib3
import multiprocessing
from tqdm import tqdm
import re
from time import sleep
import socket


# Usage of globals is bad, I know. I use them so I don't have to keep
# re-entering my creds with every function call, and without needing
# to store plaintext creds. I can't use keyring because I haven't
# figured out how to use it on my headless jumphost.
network_username = ''
network_password = ''
telnet_password = ''
secret = ''
orion_username = ''
orion_password = ''

# Number of threads for concurrent sessions.
# Typically, multiprocessing pools are set to use the number of cores
# available on the server. However, in our case, the threads are not
# CPU-intensive, so we can get away with a lot more. Experimentation has shown
# that 40 strikes a good balance. Fewer means slower performance, more means
# maxing out system resources.
THREADS = 40


class NetmonkeyError(Exception):
    """ Base class for exceptions in this module. """
    pass

class HostOfflineError(NetmonkeyError):
    """ Raised when an attempt is made to connect to a host that is not
       network reachable.

    Attributes:
        host -- the hostname or IP that was attempted
        msg  -- explanation of the error
    """

    def __init__(self, host, msg):
        self.host = host
        self.msg = msg

class NoOpenPortError(NetmonkeyError):
    """ Raised when an attempt is made to connect to a host that does
        not have either SSH or telnet available (ports 22 or 23, respectively).

    Attributes:
        host -- the hostname or IP that was attempted
        msg  -- explanation of the error
    """

    def __init__(self, host, msg):
        self.host = host
        self.msg = msg

class InvalidCommandTypeError(NetmonkeyError):
    """ Raised when a command type is given that is not either 'show' or 'config'
    """

    def __init__(self, msg):
        self.msg = msg

# http://mattoc.com/python-yes-no-prompt-cli.html
def prompt(query):
    """ Returns boolean for y/n input """
    print '%s [y/n]: ' % query
    val = raw_input()
    try:
        ret = strtobool(val)
    except ValueError:
        print 'Reply with y/n'
        return prompt(query)
    return ret

def get_creds():
    """ Prompts for credentials that are stored in global variables for reuse
    """
    global default_username
    global network_username
    global network_password
    global telnet_password
    global secret
    default_username = getuser()
    if not network_username or not network_password or not telnet_password or not secret:
        network_username = raw_input('Network username [' + default_username + ']: ') or default_username
        network_password = getpass('Network password: ')
        telnet_password = getpass('Telnet password: ') or None
        secret = getpass('Enable secret: ')

def orion_init():
    """ Prompts for Orion credentials and returns a SwisClient object
    """
    global orion_server
    global orion_username
    global orion_password
    if not orion_username:
        default_username = getuser()
        orion_username = raw_input('Orion username [' + default_username + ']: ') or default_username
    if not orion_password:
        orion_password = getpass('Orion password: ')
    # SolarWinds-Orion is a special hostname in /etc/hosts
    # This was necessary to implement SSL checking
    # https://github.com/solarwinds/orionsdk-python#ssl-certificate-verification
    # this disables the SubjectAltNameWarning
    urllib3.disable_warnings()
    # TODO: Need a better/more resilient way of referencing server cert.
    return orionsdk.SwisClient('SolarWinds-Orion', orion_username, orion_password, verify='server.pem')

def get_devices(*args, **kwargs):
    """ Retrieve a list of hosts for later use.
    
    TODO:
    Ideally this will be able to handle:
     - An SWQL query directly from Orion
     - A CSV
     - A flat text file of hostnames/IPs
    """

    if args:
        # Single host
        if type(args[0]) is str:
            # Returns as a single-item list
            # This is important since most methods below iterate,
            # and a string is not iterable.
            return args[0].split()
        # If hosts given as list, simply return that list again
        elif type(args[0]) is list or type(args[0]) is dict:
            return args[0]
    # TODO: If source is a file, read that
    elif args and os.path.isfile(str(args[0])):
        pass
    # Otherwise assume the source is a SWQL query
    elif kwargs:
        # Initialize Orion connection
        swis = orion_init()
     
        # Read base query from file
        # TODO: This seems wrong. Not sure how to abstract the base SWQL query
        # properly. Should it be a file or somehow hardcoded?
        module_dir = os.path.split(os.path.abspath(__file__))[0]
        base_query_file = open(module_dir + '/base-query.swql')
        query = base_query_file.read()
        base_query_file.close()

        # Can't append this to the query until we have all filters in place
        query_order = "ORDER BY Caption\n"

        query += 'AND '
        query_filter = []
        district = kwargs.get('district')
        site = kwargs.get('site')
        name = kwargs.get('name')
        if district:
            query_filter.append("Nodes.CustomProperties.School_District = '%s'\n" % district)
        if site:
            query_filter.append("Nodes.CustomProperties.School_Site = '%s'\n" % site)
        if name:
            name = name.replace('*', '%')
            query_filter.append("Caption LIKE '%s'\n" % name)
        query += ' AND '.join(query_filter)
        query += query_order
        return (swis.query(query))['results']

def is_online(host):
    """ Pings hostname once and returns true if response received. """
    # '> /dev/null 2>&1' redirects stderr to stdout, and stdout to null.
    # In other words, print nothing at all.
    response = os.system('ping -q -c 1 ' + host + ' > /dev/null 2>&1')
    if response == 0:
        return True
    else:
        raise HostOfflineError(host, 'Host is not network-reachable.')
        return False

def check_proto(host):
    """ Checks if port 22 or 23 is open, and returns open port number. """
    check = socket.socket()
    response = check.connect_ex((host, 22))
    if response == 0:
        return {'port': 22, 'name': 'ssh'}
    else:
        response = check.connect_ex((host, 23))
        if response == 0:
            return {'port': 23, 'name': 'telnet'}
        else:
            raise NoOpenPortError(host, 'Neither port 22 nor 23 is open.')

def sanitize_host(host):
    """ Removes extraneous characters from a hostname, leaves an IP untouched. """
    if re.match(r'[a-zA-Z]', host):
        return host.split()[0].strip().replace('_', '-').replace('.', '')
    else:
        return host

def connect(host):
    """ Opens an SSH/telnet session with an online host.
    
        Returns session object, or exception if none could be created.
    """
    global network_username
    global network_password
    global telnet_password
    global secret
    get_creds()
    if is_online(host):
        open_proto = check_proto(host)
        if open_proto:
            device = {
                'device_type': 'cisco_ios_' + open_proto['name'],
                'ip': host,
                'username': network_username,
                'password': network_password,
                'secret': secret,
                'port': open_proto['port'],
                'verbose': False
            }
            try:
                return netmiko.ConnectHandler(**device)
            except netmiko.ssh_exception.NetMikoAuthenticationException:
                # If my creds are rejected, try the generic telnet password
                device['password'] = telnet_password
                try:
                    return netmiko.ConnectHandler(**device)
                except netmiko.ssh_exception.NetMikoAuthenticationException:
                    # If we still can't log in, nothing more to try
                    raise
            except:
                raise

def write_config(session):
    return session.send_command_expect('copy running-config startup-config')

def backup_config(session):
    """ Runs custom alias to back up config via TFTP
    
    Reference: https://github.com/ktbyers/netmiko/issues/330
    """
    output = session.send_command_timing('backup')

    # Our backup alias expects two [enter] keystrokes
    if '?' in output:
        output += session.send_command_timing('\n')
        output += session.send_command_timing('\n')
    return output

def show(cmd, target):
    """ Returns aggregate output for one or more show commands. """
    return batch(target, command, ['show', cmd])

def config(cmd, target):
    """ Writes one or more configuration commands and returns aggregate output. """
    return batch(target, command, ['config', cmd])

def run(function, target):
    """ Runs a custom function in parallel and returns aggregate output. """
    return batch(target, command, ['fn', function])

def print_results(results):
    """ Prints results from command() in human-readable format.
        Mostly useful for debugging.

    """
    for result in results:
        for hostname, output in result.iteritems():
            print hostname
            for k, v in output.iteritems():
                print " - %s: %s" % (k, v)

def command(target, cmd_type, cmd, result_list=None):
    """ Runs arbitrary commands or functions against a single target device. """

    # TODO
    # If command() is called by batch(), batch() absolutely needs command()
    # to append *something* to result_list, or else it will stay stuck waiting
    # for results.

    # However, if command() is called independently of batch(), we don't care
    # and just want the output returned. I tried several methods of accommodating
    # both cases, but ended up with this. If result_list hasn't been passed,
    # create an empty list and append output to it.
    if result_list == None:
        result_list = []

    # Return data structure:
    # hostname = {port, status, message}
    # Port
    # - 22 or
    # - 23
    # Status:
    # - 0: Success
    # - 1: Host offline
    # - 2: Ports 22 and 23 are both closed
    # - 3: Invalid credentials
    # - 4+: Available for use in custom functions
    # Message:
    # - if status == 0, the result of command(s) given
    # - if status != 0, description of error

    return_data = {}
    
    if cmd_type not in ['show', 'config', 'fn']:
        raise InvalidCommandTypeError('cmd_type must be either "show", "config", or "fn"')
    
    # TODO: If cmd is a file, send batch file
    # If we received the target via SWQL query, we need to parse the dictionary
    # to get the actual hostname or IP.
    # The other fields of the query such as Location are not used here, but could
    # be used if they were ever helpful.
    if type(target) is dict:
        host = target['Caption']
        ipaddress = target['IPAddress']
        location = target['Location']
    else:
        host = target

    session = None
    
    # Orion sometimes contains invalid characters in hostnames.
    host = sanitize_host(host)

    try:
        session = connect(host)
    except HostOfflineError as e:
        return_data[host] = {
            'port': None,
            'status': 1,
            'message': e.msg
        }
        pass
    except NoOpenPortError as e:
        return_data[host] = {
            'port': None,
            'status': 2,
            'message': e.msg
        }
        pass
    except netmiko.ssh_exception.NetMikoAuthenticationException as e:
        # I can get the port from the session object if it's created,
        # but if there is no session object, I have to infer the port that
        # was attempted from the authentication exception.
        # This seems ugly to me, it seems even uglier to me to do something
        # with connect(), which, I feel, behaves as it should.
        # Otherwise, check to see if we are parsing by district/site
        
        error = str(e)
        if '_ssh' in error:
            port = 22
        if 'Telnet' in error:
            port = 23
        else:
            port = None
        return_data[host] = {
            'port': port,
            'status': 3,
            'message': error
        }
        pass
    
    if session:
        # If we have been passed an actual function as cmd_type, call that
        # function with the session variable passed.
        # TODO: It might be nice to allow custom functions to be passed
        # arbitrary arguments, not just the session object.
        if cmd_type == 'fn':
            output = cmd(session)
        # Otherwise, proceed to run the commands literally as show or config
        # commands.
        else:
            session.enable()
            if cmd_type == 'config':
                session.config_mode()
            if cmd_type == 'show':
                cmd = 'show ' + cmd
            output = session.send_command(cmd)
            if cmd_type == 'config':
                write_config(session)
                backup_config(session)
            session.disconnect()
    
        return_data[host] = {
            'port': session.port,
            'status': 0,
            'message': output
        }
    else:
        return_data[host] = {
            'port': None,
            'status': 4,
            'message': 'Unknown error occurred, sorry.'
        }
        
    # Since the result_list is passed as an empty list,
    # we can't just do `if result_list:`, which evaluates to false.
    # (Since an empty list evaluates to false, even though the variable
    # exists)
    # Basically, if the result_list argument is passed, used it,
    # otherwise, return return_data directly.
    #if 'result_list' in locals():
    #    result_list.append(return_data)
    #else:
    #    return return_data

    result_list.append(return_data)
    return return_data

def batch(targets, worker, argument_list=None, threads=THREADS):
    """ Parallelizes an arbitrary function against arbitrary target devices.

        When running commands against hundreds or thousands of devices,
        creating simultaneous sessions would exhaust system resources.
        This approach ensures that resources are used maximally, neither
        under-using or over-using them.
    
    """
    # Get credentials and devices
    get_creds()
    targets = get_devices(targets)
    
    # Initialize work pool
    pool = multiprocessing.Pool(threads)
    manager = multiprocessing.Manager()
    result_list = manager.list()
    
    # For all targets, add a job to the pool
    for target in targets:
        if not argument_list:
            worker_args = [target, result_list]
        else:
            # If we have been passed an argument list, we need to insert
            # that into the arguments we pass to the worker function
            worker_args = argument_list[:]
            worker_args.insert(0, target)
            worker_args.append(result_list)
        pool.apply_async(worker, args = tuple(worker_args))
    
    # Closing the pool means no other jobs will be submitted
    pool.close()

    # Progress bar

    # tqdm() is much simpler if you can call an iterable with it.
    # As far as I can tell, nothing about the pool semantics above
    # use an iterable that actually represents the progress of work done.
    # The one loop above only queues jobs, it doesn't acutally track them.
    # This construct below makes our own progress bar.

    # TODO: This just isn't acceptable. There needs to be some kind of timeout
    # so a single failed thread doesn't hang the whole job. I know there is 
    # a timeout argument in the get() method of queues, look into that.
    pbar = tqdm(total=len(targets), desc='Progress', unit='Device', ascii=True)
    progress = 0
    while len(result_list) <= len(targets):
        pbar.update(len(result_list) - progress)
        progress = len(result_list)
        if progress == len(targets):
            break
        # Check for progress updates every half second
        sleep(0.5)
    pbar.close()

    return result_list
