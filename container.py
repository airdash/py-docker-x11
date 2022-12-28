import os, sys, time
import stat
import docker
import tarfile
import io
import glob, evdev
import re
import dockerpty
import subprocess
from pathlib import Path
from util import user

class Container:
    def __init__(self):
        self.devices = []
        self.device_cgroup_rules = []
        self.mounts = {}
        self.environment = {}
        self.audio = { "enabled": False }
        self.hwrender = { "enabled": False }
        self.joystick = { "enabled": False }
        self.webcam = { "enabled": False }
        self.other_devices = {}

    def buildMounts(self):

        container_uid = self.config.get("container", "user_uid")
        container_gid = self.config.get("container", "user_gid")

        full_profile_dir = os.path.join(self.config.safe_get("profileDir"), self.config.safe_get("profileUser"), 
                                        self.config.safe_get("platform"), self.config.safe_get("appconfig", "app_name"))

        if self.config.get("subprofileUser"):
            full_profile_dir = os.path.join(full_profile_dir, self.config.get("subprofileUser"))

        print ("[DEBUG] self.config.getMounts() is: %s" % self.config.getMounts())
        if self.config.getMounts() is not None and not self.config.get("no_mount"):
            for mount, mountpoint in self.config.getMounts().items():
                print("[DEBUG] mountpoint is %s" % type(mountpoint))
                print("[DEBUG] mountpoint is %s" % str(mountpoint))
                mount = re.sub("_full_profile_dir", full_profile_dir, mount)
                if isinstance(mountpoint, str):
                    print("Setting mount => mountpoint %s %s" % (mount, mountpoint))
                    self.mounts[mount] = mountpoint

                    if not os.path.exists(str(mount)):
                        print("Creating directory %s" % str(mount))
                        os.makedirs(mount)
                        print("Chowning directory %s" % str(mount))
                        user.chown(mount, container_uid, container_gid)

                elif isinstance(mountpoint, dict):
                    print("Dict mount is %s" % str(mount))
                    self.mounts[mount] = mountpoint
                    if mountpoint.get("type") == "file":
                        # Prevents inability to start container because we're mounting a directory over a file
                        if not os.path.exists(str(mount)):
                                mountfile = Path(str(mount))
                                mountfile.touch()
                                user.chown(mount, container_uid, container_gid)
                    elif not os.path.exists(str(mount)):
                        print("Creating directory %s" % str(mount))
                        os.makedirs(mount)
                        print("Chowning directory %s" % str(mount))
                        user.chown(mount, container_uid, container_gid)
                else:
                    print("[ERROR] An issue occured setting up the container mounts!")
                    print("mountpoint is instance of %s" % type(mountpoint))

        if self.config.getDeviceConfig("audio").get("enabled") is True and self.config.getDeviceConfig("audio").get("pasocket"):
            print("Audio is enabled.")    
            pasocket = self.config.getDeviceConfig("audio").get("pasocket")
            print("pasocket is %s" % pasocket)
            self.mounts[pasocket] = pasocket
            self.environment["PULSE_SERVER"] = pasocket

        if self.config.getDeviceConfig("hwrender").get("enabled") == True:
            for videoDevice in self.getVideoDevices():
                self.devices.append(videoDevice + ":" + videoDevice)
            self.devices.append("/dev/vga_arbiter:/dev/vga_arbiter")
            self.devices.append("/dev/dri:/dev/dri")

        if self.config.getDeviceConfig("joystick").get("enabled") == True:
            print("Joystick is enabled.")
            js_devices, ev_devices = self.getJoysticks()

            if not self.config.getDeviceConfig("joystick").get("single"):
                for joystick in js_devices + ev_devices:
                    self.devices.append(joystick + ":" + joystick)
                    # self.device_cgroup_rules.append(self.get_device_cgroup_rule(joystick))
            else:
                try:
                    device_number = self.config.getDeviceConfig("joystick").get("deviceNumber") - 1
                    self.devices.append(js_devices[device_number] + ":" + js_devices[device_number])
                    self.devices.append(ev_devices[device_number] + ":" + ev_devices[device_number])
                    # self.device_cgroup_rules.append(self.get_device_cgroup_rule(js_devices[device_number]))
                    # self.device_cgroup_rules.append(self.get_device_cgroup_rule(ev_devices[device_number]))

                except IndexError:
                    print("Requested joystick number not found! Continuing anyways.")

            # FIXME - Figure out how to generate this on the fly?
            if self.config.getDeviceConfig("joystick").get("sdl"):
                self.environment["SDL_GAMECONTROLLERCONFIG"] = self.config.getDeviceConfig("joystick").get("sdl_config")
                self.mounts["/run/udev"] = "/run/udev"

        if self.config.getDeviceConfig("webcam"):
            print("self.config.getDeviceConfig(webcam) is %s" % self.config.getDeviceConfig("webcam"))
            if self.config.getDeviceConfig("webcam").get("enabled") == True:
                print("Webcam is enabled.")
                for device_glob in [ "media", "video", "hidraw" ]:
                    print("Checking for device glob %s" % device_glob)
                    webcam_devices = glob.glob("/dev/" + device_glob + "*")
                    print("Webcam devices:")
                    print(webcam_devices)
                    if device_glob == "hidraw":
                        pass
                    #     webcam_devices.sort()
                    #     print("Sorted devices:")
                    #     print(webcam_devices)
                    #     device = webcam_devices[-1]
                    #     self.devices.append(device + ":" + device)
                    else: 
                        for device in webcam_devices:
                            self.devices.append(device + ":" + device)
                if os.path.exists("/dev/v4l"):
                    self.mounts["/dev/v4l"] = "/dev/v4l"

                self.mounts["/run/udev/data"] = "/run/udev/data"

        if self.config.get("display_server") == "wayland":
            try:
                self.mounts["/run/user/1000/wayland-0"] = "/tmp/xdg_runtime_dir/wayland-0"
            except:
                print("Could not mount XDG_RUNTIME_DIR into the container")
        else:
            try:
                os.path.isfile("/tmp/.X11-unix")
                print("X11 socket found")
                self.mounts["/tmp/.X11-unix"] = "/tmp/.X11-unix"
            except FileNotFoundError:
                print("X11 socket not found! Check that /tmp/.X11-unix exists.")
                sys.exit(1)
        
        if self.config.getDeviceConfig("other"):
            print("self.config.getDeviceConfig-other is %s" % self.config.getDeviceConfig("other"))
            for device in self.config.getDeviceConfig("other"):
                self.mounts[device] = device

    def runContainer(self, client):
        self.container_config = self.config.getContainerConfig()
        container_args = {}
        container_config = {}
        host_config = {}
        host_config["group_add"] = []
        network_config = {}

        container_args["image"] = self.container_config["image"] + ":" + self.container_config.get("tag", "latest")
        container_entrypoint = client.inspect_image(container_args["image"])["Config"]["Entrypoint"]

        if container_entrypoint and not self.container_config.get("entrypoint"):
            self.container_config["entrypoint"] = container_entrypoint
            if self.container_config["entrypoint"] == [ "/bin/sh", "-v", "-c" ]:
                shell_entrypoint = True
            else:
                shell_entrypoint = False
            container_args["entrypoint"] = self.container_config.get("entrypoint")

        elif self.container_config.get("entrypoint"):
            container_args["entrypoint"] = self.container_config.get("entrypoint")
            shell_entrypoint = False

        else:
            container_args["entrypoint"] = [ "/bin/sh", "-v", "-c" ]
            shell_entrypoint = True

        container_command = client.inspect_image(container_args["image"])["Config"]["Cmd"]

        if container_command and not self.container_config.get("command"):
            self.container_config["command"] = container_command
            container_args["command"] = container_command

        if self.container_config.get("command") is not None and self.container_config.get("entrypoint_override") is not True and shell_entrypoint:
            if isinstance(self.container_config["command"], list):
                container_args["command"] = "\"" + "/home/sandbox/pre_run.sh" + " && " + " ".join(self.container_config["command"]) + "\""
            else:
                container_args["command"] = "\"" + "/home/sandbox/pre_run.sh" + " && " + self.container_config["command"] + "\""

        elif self.container_config.get("entrypoint_override") is True:
            container_args["command"] = []

        if self.container_config.get("argv") and shell_entrypoint:
            args = " ".join(self.container_config.get("argv"))

            # This is a nightmare, and there HAS to be a better way of doing it.
            # "Fixes" quoting in shell arguments with parens, spaces, etc
            args = re.sub('([^\']$)', '\\1\'', args)
            args = re.sub('([^\']\S) (/[^\']\S)', '\\1\' \'\\2', args)
            args = re.sub('([^\']) (-\w)', '\\1\' \\2', args)
            args = re.sub('([^\']) (--\w+)', '\\1', args)
            args = re.sub("(-[A-Za-z0-9])'", '\\1', args)
            args = re.sub("(--[A-Za-z0-9]+)'", '\\1', args)

            container_args["command"] = re.sub("\"$", "", container_args["command"]) + " " + args + "\""

        if self.container_config.get("workingDir") is not None:
            container_args["working_dir"] = self.container_config.get("workingDir")

        if self.container_config.get("shm_size") is not None:
            host_config["shm_size"] = self.container_config.get("shm_size")

        if self.config.getDeviceConfig("webcam"):
            if self.config.getDeviceConfig("webcam").get("enabled") == True:
                host_config["group_add"].append("video")

        if self.container_config.get("seccomp_profile") is not None:
            # This expects a file
            if (self.config.get("seccomp_dir")):
                if os.path.exists(os.path.join(self.config.get("seccomp_dir"), self.container_config.get("seccomp_profile"))):
                    seccomp = open(os.path.join(self.config.get("seccomp_dir"), self.container_config.get("seccomp_profile")))
                    host_config["security_opt"] = [ "seccomp=" + " ".join(seccomp.read().splitlines()) ]
            elif os.path.exists(self.container_config.get("seccomp_profile")):
                seccomp = open(self.container_config.get("seccomp_profile"))
                host_config["security_opt"] = [ "seccomp=" + " ".join(seccomp.read().splitlines()) ]
            else:
                # Bail since we don't want to run a container that expects a security profile but can't find one!
                print("Seccomp profile not found: %s / %s - Aborting!" % (self.config.get("seccomp_dir"), self.container_config.get("seccomp_profile")))
                sys.exit(1)

        container_args["image"] = self.container_config["image"] + ":" + self.container_config.get("tag", "latest")
        container_args["ports"] = [ key for key in self.container_config.get("ports") or []]
        container_args["detach"] = False

        if self.container_config.get("tty") == True:
            container_args["tty"] = True

        if self.container_config.get("workdir"):
            container_args["working_dir"] = self.container_config.get("workdir")

        if self.container_config.get("stdin_open") == True:
            container_args["stdin_open"] = True

        # This requires docker-py as per PR #2465 from Ryan Leary
        # This also allows Vulkan to run in a user namespace, otherwise X tends to crash.

        # if self.container_config.get("gpu_hook") is not None:
        #     if self.container_config["gpu_hook"].get("enabled") is True:
        #         host_config["device_requests"] = [ docker.types.DeviceRequest(count=-1, capabilities=[['gpu']]) ]

        if self.config.get("display_server") == "wayland":
            self.container_config["environment"].pop("DISPLAY")
        else:
            self.container_config["environment"].pop("WAYLAND_DISPLAY")

        print("self.container_config[environment] is %s" % self.container_config["environment"])
        print("self.environment is %s" % self.environment)
	
        container_args["environment"] = {**self.container_config["environment"], **self.environment}

        if self.container_config.get("environment"):
            print(self.container_config.get("environment"))
            for k,v in self.container_config.get("environment").items():
                container_args["environment"][k] = v

        if container_args.get("name") is not None:
            container_args["name"] = self.container_config["name"]
        elif self.container_config.get("name"):
            container_args["name"] = self.container_config.get("name")
        elif self.config.get("subprofileUser"):
            container_args["name"] = self.container_config["image"].replace('/', '-') + "-" + self.config.safe_get("subprofileUser")
        else:
            container_args["name"] = self.container_config["image"].replace('/', '-') + "-" + self.config.safe_get("profileUser")

        container_args["hostname"] = container_args["name"]
        host_config["auto_remove"] = True
        host_config["port_bindings"] = self.container_config.get("ports")
        host_config["binds"] = self.mounts
        host_config["devices"] = self.devices
        host_config["device_cgroup_rules"] = self.device_cgroup_rules

        networking_config = {}

        if self.config.get("container", "network_mode") == "host":
            host_config["network_mode"] = "host"
        elif self.config.get("container", "network_mode") == "none":
            host_config["network_mode"] = "none"
        else:
            if self.config.get("container", "network") is not None and self.config.get("devices", "network", "enabled") is True:
                networking_config = client.create_networking_config({
                    self.config.get("container", "network", "name"): client.create_endpoint_config()
                })

        print("Container args is %s" % container_args)
        print("Building container")

        # This is gross, FIXME
        if networking_config:
            container = client.create_container(**container_args, host_config=client.create_host_config(**host_config), networking_config=networking_config)
        else:
            container = client.create_container(**container_args, host_config=client.create_host_config(**host_config))

        # if self.config.get("container", "network") is not None and self.config.get("devices", "network", "enabled") is True:
        #     network_config["net_id"] = self.config.get("container", "network", "name")
        #     client.connect_container_to_network(container=container.get('Id'), **network_config)

        self.injectConfigs(client, container)
        # print("Running container with entrypoint %s: " % container_args["entrypoint"])
        client.start(container=container.get('Id'))

        # Check for the process
        if self.config.getAppConfig().get("running_executable") is not None and not self.container_config.get("stdin_open"):

            while(True):
                print("Waiting on the process %s to run post_run script..." % self.config.getAppConfig().get("running_executable"))
                try:
                    subprocess.check_output(["pgrep", self.config.getAppConfig().get("running_executable")])
                    print("Found process, running script.")
                    break
                except Exception as e:
                    print("Still waiting... %s" % e)
                    time.sleep(5)
                    continue

            print("Running post_run script")
            post_run_exec = client.exec_create(container=container.get('Id'), cmd=["/bin/bash", "-c", "${HOME}/post_run.sh"])
            exec_start = client.exec_start(exec_id=post_run_exec, stream=True)

            for msg in exec_start:
                print(msg)

        if container_args.get("stdin_open"):
            print("Entering interactive mode.")
            dockerpty.start(client, container=container.get('Id'))

        client.wait(container=container.get('Id'))

    def injectConfigs(self, client, container):
        for file, script in self.config.getScripts().items():

            current_script = script

            # Append 
            if file == "pre_run":
                current_script = "#!/bin/sh" + "\n\n" + current_script + "\n" + "exec \"$@\"" + "\n"

            script_buffer = current_script.encode('utf8')

            script_tarinfo = tarfile.TarInfo(name=file + ".sh")
            script_tarinfo.size = len(script_buffer)
            script_tarinfo.mode = 493

            tar_object = io.BytesIO()

            f = tarfile.open(fileobj=tar_object, mode='w')
            f.addfile(script_tarinfo, io.BytesIO(script_buffer))
            f.close()

            tar_object.seek(0)

            client.put_archive(container=container['Id'], path=os.path.join("/home", self.container_config["user"]), data=tar_object)

    def setConfig(self, config):
        self.config = config

    def getVideoDevices(self):
        if os.path.exists('/dev/nvidia0') and os.path.exists('/dev/nvidiactl'):
            print("Found nVidia card running binary drivers")
            return [ "/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-modeset", "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools" ]
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
            print("Evaluating device %s" % device)
            if re.search('x.box', device.name, re.IGNORECASE):
                print("Found xbox joystick device at %s" % device.fn)
                ev_devices.append(device.fn)
            elif re.search('Wireless Controller', device.name, re.IGNORECASE):
                print("Found playstation joystick device at %s" % device.fn)
                ev_devices.append(device.fn)
            elif re.search('DualShock 4', device.name, re.IGNORECASE):
                print("Found playstation joystick device at %s" % device.fn)
                ev_devices.append(device.fn)
            elif re.search('Sony Interactive Entertainment Wireless Controller', device.name, re.IGNORECASE):
                print("Found playstation joystick device at %s" % device.fn)
                ev_devices.append(device.fn)

        return js_devices, ev_devices

    def get_device_cgroup_rule(self, device, mode="rmw"):
        print("Getting info for %s" % device)
        info = os.lstat(device)
        print(info)
        if stat.S_ISBLK(info.st_mode):
            device_type = "b"
        elif stat.S_ISCHR(info.st_mode):
            device_type = "c"

        device_major = str(os.major(info.st_rdev))
        device_minor = str(os.minor(info.st_rdev))

        print("=== Adding rule: %s ===" % (device_type + " " + device_major + ":" + device_minor + " " + mode))
        return(device_type + " " + device_major + ":" + device_minor + " " + mode)
