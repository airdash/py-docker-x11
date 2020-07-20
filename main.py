#!/usr/bin/env python3

import os, sys, subprocess, glob, signal
import tarfile, io
import evdev, tarfile
import yaml, jinja2
import docker
import argparse
import pprint
import time, re
import daemon 

class Supervisor:
    def __init__(self, config):
        self.container = Container()
        self.config = config

    def controlHTPC(self, command):
        try:
            # Some versions of some HTPC software still receive events when they lose focus
            # So let's stop/start the process to get around this.
            pid = int(subprocess.check_output(["pidof", self.config["htpc"]["binary"]]))
            signals = { "stop" : signal.SIGSTOP, "start" : signal.SIGCONT }
            os.kill(pid, signals[command])
        except:
            print("HTPC process not found. Ignoring control command: %s" % command)

    def run(self):
        self.container.setConfig(self.config)
        self.container.buildMounts()
        # self.container.buildWrapper()

        if self.config["htpc"]["enabled"] == True:
            self.controlHTPC("stop")

        with daemon.DaemonContext():
            self.container.runContainer()
        # self.monitorContainer(self.container)
        
        if self.config["htpc"]["enabled"] == True:
            self.controlHTPC("start")

class Application:
    def __init__(self):
        self.appname = ""
        self.exepath = ""
        self.executable = ""
        self.running_executable = ""
        self.internal_app_dir = ""
        self.program_args = ""
        self.wrapper = ""
        self.platform_options = {}

class Container:
    def __init__(self):
        self.mounts = []
        self.audio = { "enabled": False }
        self.hwrender = { "enabled": False }
        self.joystick = { "enabled": False }
        self.network = { "enabled": True }

    def buildMounts(self):
        self.config["container"]["devices"] = []

        if self.config["devices"]["audio"]["enabled"] == True:
            if self.getPASocket(self.config["paSocket"]):
                self.config["container"]["mounts"][self.config["paSocket"]] = self.config["paSocket"]

        if self.config["devices"]["hwrender"]["enabled"] == True:
            for videoDevice in self.getVideoDevices():
                self.config["container"]["devices"].append(videoDevice + ":" + videoDevice)

        if self.config["devices"]["joystick"]["enabled"] == True:
            js_devices, ev_devices = self.getJoysticks()

            if not self.config["devices"]["joystick"]["single"]:
                for joystick in js_devices + ev_devices:
                    self.config["container"]["devices"].append(joystick + ":" + joystick)
            else:
                device_number = self.config["devices"]["joystick"]["deviceNumber"] - 1
                self.config["container"]["devices"].append(js_devices[device_number]) 
                self.config["container"]["devices"].append(ev_devices[device_number]) 

            # FIXME - Figure out how to generate this on the fly?
            if self.config["devices"]["joystick"]["sdl"]:
                self.config["container"]["environment"]["SDL_GAMECONTROLLERCONFIG"] = self.config["devices"]["joystick"]["sdl_config"]

        try:
            os.path.isfile("/tmp/.X11-unix")
            self.config["container"]["mounts"]["/tmp/.X11-unix"] = "/tmp/.X11-unix"
        except FileNotFoundError:
            print("X11 socket not found! Check that /tmp/.X11-unix exists.")
            sys.exit(1)
    
    def runContainer(self):
        client = docker.APIClient()

        if isinstance(self.config["container"]["entrypoint"], list):
            command = " ".join(self.config["container"]["entrypoint"])
        else:
            command = self.config["container"]["entrypoint"]

        ports = [ key for key in self.config["container"]["ports"] or []]
        container = client.create_container(image=self.config["container"]["image"] + ":" + self.config["container"]["tag"],
                                            entrypoint=[self.config["container"]["init"], "-v", "--"],
                                            command=["bash", "-c", "${HOME}/pre_run.sh && exec " + command],
                                            ports=ports, detach=False,
                                            environment=self.config["container"]["environment"],
                                            working_dir=self.config["container"]["workingDir"],
                                            host_config=client.create_host_config(
                                                port_bindings=self.config["container"]["ports"],
                                                binds=self.config["container"]["mounts"],
                                                devices=self.config["container"]["devices"]
                                            ))

        # Inject scripts into container                                    
        for script in [ "pre_run", "post_run", "post_exit"]:

            print("Processing %s, which is %s" % (script, self.config["scripts"][script]))
            current_script = self.config["scripts"][script]
            script_buffer = current_script.encode('utf8')

            script_tarinfo = tarfile.TarInfo(name=script + ".sh")
            script_tarinfo.size = len(script_buffer)
            script_tarinfo.mode = 493

            tar_object = io.BytesIO()

            f = tarfile.open(fileobj=tar_object, mode='w')
            f.addfile(script_tarinfo, io.BytesIO(script_buffer))
            f.list()
            f.close()

            tar_object.seek(0)

            client.put_archive(container=container['Id'], path='/home/sandbox', data=tar_object)

        client.start(container=container.get('Id')) 

        # Check for the process
        while(True):
            print("Waiting on the process %s to run post_run script..." % self.config["appconfig"]["runningExecutable"])
            time.sleep(5)
            try:
                subprocess.check_output(["pidof", self.config["appconfig"]["runningExecutable"]])
            except:
                continue
            finally:
                break

        print("Running post_run script")
        # client.containers.exec_run(container=container.get('Id'), cmd=["exec", "${HOME}/post_run.sh"])
        client.wait(container=container.get('Id'))
        
    def setConfig(self, config):
        self.config = config

    def getVideoDevices(self):
        if os.path.exists('/dev/nvidia0') and os.path.exists('/dev/nvidiactl'):
            print("Found nVidia card running binary drivers")
            return [ "/dev/nvidia0", "/dev/nvidiactl" ]
        else:
            return []
        
    def getPASocket(self, socket):
        if os.path.exists(socket):
            print("Found Pulseaudio socket at %s" % socket)
            return True
    
    def getJoysticks(self):
        js_devices = glob.glob("/dev/input/js*")
        js_devices.sort()
    
        ev_devices = []
        ev_device_list = [ evdev.InputDevice(device) for device in reversed(evdev.list_devices()) ]
        for device in ev_device_list:
            if re.search('x.box', device.name, re.IGNORECASE):
                print("Found joystick device at %s" % device.fn)
                ev_devices.append(device.fn)
    
        return js_devices, ev_devices


### From https://stackoverflow.com/questions/7204805/how-to-merge-dictionaries-of-dictionaries/7205107#7205107
class YamlReaderError(Exception):
    pass

def mergeConfig(a, b):
    try:
        if a is None or isinstance(a, str) or isinstance(a, int) or isinstance(a, float):
            a = b
        elif isinstance(a, list):
            if isinstance(b, list):
                a.extend(b)
            else:
                a.append(b)
        elif isinstance(a, dict):
            if isinstance(b, dict):
                for key in b:
                    if key in a:
                        a[key] = mergeConfig(a[key], b[key])
                    else:
                        a[key] = b[key]
            else:
                raise YamlReaderError('Cannot merge non-dict "%s" into dict "%s"' % (b, a))
        else:
            raise YamlReaderError('NOT IMPLEMENTED "%s" into "%s"' % (b, a))
    except TypeError as e:
        raise YamlReaderError('TypeError "%s" in key "%s" when merging "%s" into "%s"' % (e, key, b, a))
    return a
###

def renderConfig(config, yamlFile, delete=False, **kwargs):
    template = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(os.path.abspath(yamlFile))))
    rendered_jinja = template.get_template(os.path.basename(yamlFile)).render(kwargs)
    rendered_yaml = yaml.load(rendered_jinja)
    return mergeConfig(config, rendered_yaml)

def checkUser(user):
    # TODO: Ensure that the user specified is a user with appropriate subuid/gids, and is running Docker.
    pass

def parseArguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--app", default=None, 
                        help="Specify the app to run. Defaults to the current working directory.")
    parser.add_argument("-b", "--baseconfig", help="Specify the base configuration yaml file.")
    parser.add_argument("-c", "--command", help="Override the defined command.")
    parser.add_argument("-e", "--entrypoint", help="Override the defined entrypoint.")
    parser.add_argument("-i", "--image", help="Run a specified image")
    parser.add_argument("--platform", default=None, help="Specify the platform that the application runs under")
    parser.add_argument("-p", "--profile", default=os.getenv("USER"),
                        help="Specify the profile to run the program under.")
    parser.add_argument("--profiledir", default=None, help="Specify the directory that profiles are kept under")
    parser.add_argument("-u", "--user", help="Specify the external sandbox user to run the container under.")
    parser.add_argument("-x", "--x11", help="Run container inside of a new X11 session.")
    args = parser.parse_args()

    return args

def findAppConfig(app_dir=os.path.join(os.path.expanduser("~"), ".py-docker-x11", "apps"), app="None", platform="None"):

    # If the yaml's here, we just use it.
    if os.path.exists(os.path.join(os.getcwd(), "app_config.yaml")):
        return os.path.join(os.getcwd(), "app_config.yaml")

    # If we define a platform, we'll use that exclusively.
    if app is not None:
        if platform is not None:
            if os.path.exists(os.path.join(app_dir, platform, app, "app_config.yaml")):
                return os.path.exists(os.path.join(app_dir, platform, app, "app_config.yaml"))

        # If we don't define a platform, we go looking.
        if os.path.exists(os.path.join(app_dir)):
           # Prefer Linux profiles over other found profiles.
           for directory in glob.glob(os.path.join(app_dir, "[Ll]inux", app)):
              if os.path.exists(os.path.join(directory, "app_config.yaml")):
                return os.path.join(directory, "app_config.yaml")

        # Otherwise, seek all files under the profile directory.
        for directory in glob.glob(os.path.join(app_dir, '*', recursive=True)):
            if os.path.exists(os.path.join(directory, "app_config.yaml")):
                return os.path.join(directory, "app_config.yaml")

    # If we find nothing, bail out.
    else:
        print("app_config.yaml not found! Please place app_config.yaml in this directory or in the appropriate app directory.")
        sys.exit(1)

def main():

    args = parseArguments()
    uid = os.geteuid()
    current_user = os.getenv("USER")
    config = {}
    
    jinja_render_args = { "current_user": current_user}

    baseConfigDir = os.path.join("/home", "userdata", "bin", "docker-x11")

    if args.profile =='wine-update':
        user_profile = current_user
    else:
        user_profile = args.profile

    config["currentUser"] = current_user
    config["userProfile"] = user_profile
    jinja_render_args["user_profile"] = user_profile
    config = renderConfig(config, os.path.join(baseConfigDir, "base_config.yaml"), **jinja_render_args)
    jinja_render_args["container_user"] = config["container"]["user"]
    jinja_render_args["profile_dir"] = config["profile_directory"]

    # Build appconfig search criteria
    appconfig = findAppConfig(app_dir=config["app_directory"], app=args.app, platform=args.platform)

    config = renderConfig(config, appconfig, **jinja_render_args)

    if os.path.isfile(os.path.join(config["profile_directory"], config["platform"], config["appconfig"]["appname"], user_profile, "profile_config.yaml")):
        config = renderConfig(config, os.path.join(config["profile_directory"],config["platform"], config["appconfig"]["appname"], user_profile, "profile_config.yaml"), **jinja_render_args)

        # Allow user profile to point to another user_profile, and rebuild the configuration accordingly
        while config["userProfile"] != user_profile:
            user_profile = config["userProfile"]
            jinja_render_args["user_profile"] = user_profile
            config = {}
            config = renderConfig(config, os.path.join(baseConfigDir, "base_config.yaml"), **jinja_render_args)
            config = renderConfig(config, appconfig, **jinja_render_args)
            if os.path.isfile(os.path.join(config["profile_directory"], config["platform"], config["appconfig"]["appname"], user_profile, "profile_config.yaml")):
                config = renderConfig(config, os.path.join(config["profile_directory"], config["platform"], config["appconfig"]["appname"], user_profile, "profile_config.yaml"), **jinja_render_args)

    #TODO: Separate this out per platform in a smart way
    if config["platform"] == "wine":
        import wine as platform
 
    config = platform.configure(config)

    if args.profile =='wine-update':
        config["container"]["entrypoint"] = "/usr/bin/wineboot -u"

    # print("Run complete. Below is the complete config.")
    # pp = pprint.PrettyPrinter(indent=4)
    # pp.pprint(config)

    if args.entrypoint:
        config["container"]["entrypoint"] = args.entrypoint

    supervisor = Supervisor(config)
    supervisor.run()

if __name__ == '__main__':
    main()
