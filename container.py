import os, sys, time
import docker
import tarfile
import io
import glob, evdev
import re
import dockerpty

class Container:
    def __init__(self):
        self.devices = []
        self.mounts = {}
        self.environment = {}
        self.audio = { "enabled": False }
        self.hwrender = { "enabled": False }
        self.joystick = { "enabled": False }

    def buildMounts(self):

        if self.config.getMounts() is not None:
            for mount, mountpoint in self.config.getMounts().items():
                self.mounts[mount] = mountpoint

        if self.config.getDeviceConfig("audio").get("enabled") is True and self.config.getDeviceConfig("audio").get("pasocket"):
            print("Audio is enabled.")    
            pasocket = self.config.getDeviceConfig("audio").get("pasocket")
            print("pasocket is %s" % pasocket)
            self.mounts[pasocket] = pasocket

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
            else:
                try:
                    device_number = self.config.getDeviceConfig("joystick").get("deviceNumber") - 1
                    self.devices.append(js_devices[device_number] + ":" + js_devices[device_number])
                    self.devices.append(ev_devices[device_number] + ":" + ev_devices[device_number])
                except IndexError:
                    print("Requested joystick number not found! Continuing anyways.")

            # FIXME - Figure out how to generate this on the fly?
            if self.config.getDeviceConfig("joystick").get("sdl"):
                self.environment["SDL_GAMECONTROLLERCONFIG"] = self.config.getDeviceConfig("joystick").get("sdl_config")

        try:
            os.path.isfile("/tmp/.X11-unix")
            print("X11 socket found")
            self.mounts["/tmp/.X11-unix"] = "/tmp/.X11-unix"
        except FileNotFoundError:
            print("X11 socket not found! Check that /tmp/.X11-unix exists.")
            sys.exit(1)

    def runContainer(self, client):
        self.container_config = self.config.getContainerConfig()
        container_args = {}
        host_config = {}
        network_config = {}

        if self.container_config.get("command") is not None:
            if isinstance(self.container_config["command"], list):
                container_args["command"] = [ "bash", "-c", "${HOME}/pre_run.sh && exec", " ".join(self.container_config["command"])]
            else:
                container_args["command"] = [  "bash", "-c", "${HOME}/pre_run.sh && exec", self.container_config["command"]]

        if self.container_config.get("entrypoint") is not None:
            container_args["entrypoint"] = self.container_config.get("entrypoint")

        if self.container_config.get("workingDir") is not None:
            container_args["working_dir"] = self.container_config.get("workingDir")

        container_args["image"] = self.container_config["image"] + ":" + self.container_config.get("tag", "latest")
        container_args["ports"] = [ key for key in self.container_config.get("ports") or []]
        container_args["detach"] = False

        if self.container_config.get("tty") == True:
            container_args["tty"] = True

        if self.container_config.get("stdin_open") == True:
            container_args["stdin_open"] = True

        container_args["environment"] = self.container_config["environment"]

        if container_args.get("name") is not None:
            container_args["name"] = self.container_config["name"]

        host_config["auto_remove"] = False
        host_config["port_bindings"] = self.container_config.get("ports")
        host_config["binds"] = self.mounts
        host_config["devices"] = self.devices

        print("Building container")
        container = client.create_container(**container_args, host_config=client.create_host_config(**host_config))

        if self.config.get("container", "network") is not None and self.config.get("devices", "network", "enabled") is True:
            network_config["net_id"] = self.config.get("container", "network", "name")
            client.connect_container_to_network(container=container.get('Id'), **network_config)

        self.injectConfigs(client, container)
        client.start(container=container.get('Id'))

        # Check for the process
        if self.config.getAppConfig().get("running_executable") is not None and not self.config.get("interactive"):

            while(True):
                print("Waiting on the process %s to run post_run script..." % self.config.getAppConfig().get("running_executable"))
                try:
                    subprocess.check_output(["pidof", self.config["appconfig"]["running_executable"]])
                except:
                    time.sleep(5)
                    continue
                finally:
                    break

        print("Running post_run script")
        # client.containers.exec_run(container=container.get('Id'), cmd=["exec", "${HOME}/post_run.sh"])
        if container_args.get("stdin_open"):
            print("Entering interactive mode.")
            dockerpty.start(client, container=container.get('Id'))

        client.wait(container=container.get('Id'))

    def injectConfigs(self, client, container):
        for file, script in self.config.getScripts().items():

            current_script = script
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
            return [ "/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-modeset" ]
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

