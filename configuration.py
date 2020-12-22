import os, sys
import jinja2, yaml
import functools
import collections
import importlib
import re

class YamlReaderError(Exception):
    pass

class Config:
    def __init__(self, args, container_args, client):
        base_dir = os.path.join(os.path.expanduser("~"), ".py-docker-x11")
        current_user = os.getlogin()

        if args.profile is not None:
            profile_user = args.profile
        else:
            profile_user = current_user
        

        base_config_yamlfile = self._getBaseConfig(base_dir)
        base_config = self._renderConfig(base_config_yamlfile)

        # Overwrite current_user and profile_user via base-config
        if base_config.get("user") is not None:
            current_user = base_config["user"]
            if args.profile is None:
                profile_user = current_user

        if args.subprofile is not None:
            subprofile_user = args.subprofile
        else:
            subprofile_user = profile_user

        jinja_render_args = { 
                              "current_user" : current_user, 
                              "profile_user" : profile_user, 
                              "subprofile_user" : subprofile_user,
                              "container_user" : base_config["container"]["user"],
                              "profile_dir" : base_config["profileDir"]
                            }

        if args.image is not None:
            image = args.image.split(':')[0]
            try:
                tag = args.image.split(':')[1]
                print("tag is %s" % tag)
            except IndexError:
                tag = "latest"

            if not client.images(name=image):
                try:
                    print("Image not found locally, attempting pull from remote.")
                    client.pull(image, tag=tag)
                except:
                    print("Requested image not found, and no local image found. Exiting.")
                    sys.exit(255)
            elif base_config["container"]["always_pull"] == True:
                try:
                    print("Pulling latest image from remote.")
                    print("tag is %s" % tag)
                    client.pull(image, tag=tag)
                except:
                    print("Requested image found locally but not found in remote. Continuing.")

            if client.inspect_image(image + ":" + tag)["ContainerConfig"]["Entrypoint"]:
                print("Entrypoint is %s" % client.inspect_image(image + ":" + tag)["ContainerConfig"]["Entrypoint"])
                entrypoint = client.inspect_image(image + ":" + tag)["ContainerConfig"]["Entrypoint"]
            else:
                entrypoint = None

        else:
            image = None
            entrypoint = None

        if image is not None and self._getDockerImageAppConfig(client, image, tag):
            app_config = self._renderConfig(self._getDockerImageAppConfig(client, image, tag), **jinja_render_args)
        else:
            app_dir = base_config["appDirs"].get("default", os.path.join(os.path.expanduser("~"), ".py-docker-x11", "apps"))
            app_config_yamlfile = self._getAppConfig(app_dir, args.app, args.platform)
            app_config = self._renderConfig(app_config_yamlfile, **jinja_render_args)
 
        if app_config["appconfig"].get("use_subprofiles") == True:
            profile_config_yamlfile = self._getProfileConfig(base_config["profileDir"], profile_user, app_config["platform"], 
                                      app_config["appconfig"]["app_name"], subprofile=subprofile_user)
        else:
            subprofile_user = None
            profile_config_yamlfile = self._getProfileConfig(base_config["profileDir"], profile_user, app_config["platform"], 
                                      app_config["appconfig"]["app_name"])

        if profile_config_yamlfile:
            profile_config = self._renderConfig(profile_config_yamlfile, **jinja_render_args)
        else:
            profile_config = {}

        if profile_config.get("profileUser") is not None and profile_config.get("profileUser") is not profile_user:
            profile_user = self.config["profileUser"]
            self.__init__(self, args.app, args.platform, profile_user)

        self.config = self._mergeConfig(base_config, app_config, profile_config)

        for name, dir in self.config["appDirs"].items():
            self.config["appDirs"][name] = os.path.expanduser(dir)
        self.config["profileDir"] = os.path.expanduser(self.config["profileDir"])
        self.config["workDir"] = os.path.expanduser(self.config["workDir"])

        if self.config.get("seccomp_dir"):
            self.config["seccomp_dir"] = os.path.expanduser(self.config["seccomp_dir"])
        
        self.config["currentUser"] = current_user
        self.config["profileUser"] = profile_user
        self.config["subprofileUser"] = subprofile_user

        if args.app:
            self.config["app_name_override"] = args.app

        if entrypoint:
            print("Setting entrypoint as %s" % entrypoint)
            self.config["container"]["entrypoint"] = entrypoint

        # Handle special command line arguments
        print("[DEBUG] - Entrypoint arg is %s" % args.entrypoint)

        if args.entrypoint and args.entrypoint is not entrypoint:
            self.config["container"]["entrypoint"] = args.entrypoint

        elif args.install or args.maintenance:
            self.config["container"]["entrypoint"] = "/bin/sh"

        if args.tty or args.maintenance or args.install:
            self.config["container"]["tty"] = True

        if args.interactive or args.maintenance or args.install:
            self.config["container"]["stdin_open"] = True

        if args.install:
            self.config["install"] = True

        if args.no_mount:
            self.config["no_mount"] = True

        if args.no_state:
            self.config["no_state"] = True

        if args.maintenance or args.install:
            self.config["container"]["workdir"] = '/'
            self.config["maintenance"] = True
        
        if container_args and self.config["container"].get("entrypoint"):
            print(" ========> Entrypoint before is %s" % self.config["container"]["entrypoint"])
            print(" ========> Container args is %s" % container_args)

            if isinstance(self.config["container"]["entrypoint"], str):
                container_entrypoint = [ self.config["container"]["entrypoint"] ]
            else:
                container_entrypoint = self.config["container"]["entrypoint"]

            if isinstance(container_args, list):
                # Docker prepends script entrypoints with "/bin/sh -c" so we need to add quotes and concatinate the script with the provided
                # arguments, otherwise things don't work. I don't know if it ever prepends anything else but let's account for bash
                if (container_entrypoint[0] == "/bin/sh" or container_entrypoint[0] == "/bin/bash") and container_entrypoint[1] == "-c":
                    print("==========> STRING MANGLING GOIN ON")
                    container_entrypoint = [ container_entrypoint[0], container_entrypoint[1], (" ".join(container_entrypoint[2:]) + " " + " ".join(container_args)) ]
                else:
                    container_entrypoint.extend(container_args)
            else:
                container_entrypoint.append(container_args)

            self.config["container"]["entrypoint"] = container_entrypoint
            
            print(" ========> Entrypoint is now %s" % self.config["container"]["entrypoint"])

        print("Profile user is %s" % profile_user)
        print("Current user is %s" % current_user)

        try:
            platform = importlib.import_module("platforms." + self.getPlatform())
            platform.configure(self)
        except ModuleNotFoundError:
            print("Could not find the platform module for your platform! Please check the platforms directory and your configuration.")
            print("Continuing without configuring for the %s platform." % config.getPlatform())

    ### Based on https://stackoverflow.com/questions/7204805/how-to-merge-dictionaries-of-dictionaries/7205107#7205107
    def _mergeConfig(self, a, b, c=None):
        try:
            if a is None or isinstance(a, str) or isinstance(a, int) or isinstance(a, float):
                a = b
            elif b is None:
                return a
            elif isinstance(a, list):
                if isinstance(b, list):
                    a.extend(b)
                else:
                    a.append(b)
            elif isinstance(a, dict):
                if isinstance(b, dict):
                    for key in b:
                        if key in a:
                            a[key] = self._mergeConfig(a[key], b[key])
                        else:
                            a[key] = b[key]
                else:
                    raise YamlReaderError('Cannot merge non-dict "%s" into dict "%s"' % (b, a))
            else:
                raise YamlReaderError('NOT IMPLEMENTED "%s" into "%s"' % (b, a))

            if c is not None:
                self._mergeConfig(a, c, None)
        except TypeError as e:
            raise YamlReaderError('TypeError "%s" in key "%s" when merging "%s" into "%s"' % (e, key, b, a))
        return a
      ###

    def _renderConfig(self, yamlFile, **kwargs):
        # TODO: Validate for valid jinja2 + yaml
        if isinstance(yamlFile, str):
            template = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(os.path.abspath(yamlFile))))
            rendered_jinja = template.get_template(os.path.basename(yamlFile)).render(kwargs)
        elif isinstance(yamlFile, dict):
            template = jinja2.Environment(loader=jinja2.DictLoader(yamlFile))
            rendered_jinja = template.get_template("jinja").render(kwargs)

        rendered_yaml = yaml.load(rendered_jinja, Loader=yaml.SafeLoader)
        return rendered_yaml
    
    def _getBaseConfig(self, base_dir):

        # If the yaml's here for some reason, just use it.
        if os.path.exists(os.path.join(os.getcwd(), "base_config.yaml")):
            print("[WARN] Using base_config.yaml in current directory!")
            return os.path.join(os.getcwd(), "base_config.yaml")

        # Else, let's check the user's home directory (where it should be)
        if os.path.exists(os.path.join(os.path.join(os.path.expanduser("~"), ".py-docker-x11", "base_config.yaml"))):
            return os.path.join(os.path.join(os.path.expanduser("~"), ".py-docker-x11", "base_config.yaml"))
        else:
            print("[ERROR] Base config not found! Please put base_config.yaml in your ~/.py-docker-x11 directory.")
            sys.exit(1)

    def _getDockerImageAppConfig(self, client, image, tag):
        image_name = image + ":" + tag
        try:
            for image in client.images(name=image_name):
                if image_name in image["RepoTags"]:
                    print("[INFO] Using attached Docker jinja template.")
                    return { "jinja" : image["Labels"]["pdx-app-config"] }
        except Exception as e:
            print("An error occured looking for the Docker image. Exiting.")
            print(str(e))
            sys.exit(1)

        print("[INFO] Could not find jinja template attached to Docker image.")
        return False
  
    def _getDockerInspect(self, client, image, tag):
        return client.inspect_image(image + ":" + tag)

    def _getAppConfig(self, app_dir, app="None", platform="None"):
    
        # If the yaml's here, we just use it.
        if os.path.exists(os.path.join(os.getcwd(), "app_config.yaml")):
            print("[INFO] Using app_config.yaml in current directory.")
            return os.path.join(os.getcwd(), "app_config.yaml")
    
        # If we define a platform, we'll use that exclusively.
        if app is not None:
            if platform is not None:
                if os.path.exists(os.path.join(app_dir, platform, app, "app_config.yaml")):
                    print("[INFO] Using app_config.yaml in %s" % os.path.join(app_dir, platform, app, "app_config.yaml"))
                    return os.path.exists(os.path.join(app_dir, platform, app, "app_config.yaml"))
    
            # If we don't define a platform, we go looking.
            if os.path.exists(os.path.join(app_dir)):
               # Prefer Linux profiles over other found profiles.
               for directory in glob.glob(os.path.join(app_dir, "[Ll]inux", app)):
                  if os.path.exists(os.path.join(directory, "app_config.yaml")):
                    print("[INFO] Using app_config.yaml in %s" % os.path.join(directory, "app_config.yaml"))
                    return os.path.join(directory, "app_config.yaml")
    
            # Otherwise, seek all files under the profile directory.
            for directory in glob.glob(os.path.join(app_dir, '*', recursive=True)):
                if os.path.exists(os.path.join(directory, "app_config.yaml")):
                    print("[INFO] Using app_config.yaml in %s" % os.path.join(directory, "app_config.yaml"))
                    return os.path.join(directory, "app_config.yaml")
    
        # If we find nothing, bail out.
        else:
            print("[ERROR] app_config.yaml not found! Please place app_config.yaml in this directory or in the appropriate app directory.")
            sys.exit(1)
    
    def _getProfileConfig(self, profile_dir, user_profile, platform, app, subprofile=None):
        if subprofile:
            print("Looking for ", os.path.join(profile_dir, user_profile, platform, app, subprofile, "profile_config.yaml"))
            if os.path.exists(os.path.join(profile_dir, user_profile, platform, app, subprofile, "profile_config.yaml")):
                return os.path.join(profile_dir, user_profile, platform, app, subprofile, "profile_config.yaml")
        else:
            print("Looking for ", os.path.join(profile_dir, user_profile, platform, app, "profile_config.yaml"))
            if os.path.exists(os.path.join(profile_dir, user_profile, platform, app, "profile_config.yaml")):
                return os.path.join(profile_dir, user_profile, platform, app, subprofile, "profile_config.yaml")

        return False

    # Returns None for statements made for handling such cases
    def get(self, *args):
        return functools.reduce(lambda curr, arg: curr.get(arg) if curr else None, args, self.config)

    # Raises exception instead of returning None
    def safe_get(self, *args):
        retval = functools.reduce(lambda curr, arg: curr.get(arg) if curr else None, args, self.config)

        if retval is None:
            raise Exception("Failed to get config value %s! Something is wrong." % args)
        else:
            return retval

    def getAppConfig(self):
        return self.config.get("appconfig")

    def getAppDir(self, platform):
        return self.config.get("appDirs")

    def getBasicConfig(self):
        return self.config.get("config")

    def getBuildConfig(self):
        return self.config.get("build")

    def getContainerConfig(self):
        return self.config.get("container")

    def getDeviceConfig(self, device_type=None):
        if self.config.get("devices") is not None:
            if self.config["devices"].get(device_type) is not None:
                return self.config["devices"].get(device_type)
            else:
                print("%s is not found under devices. Check your configs and try again." % device_type)
        return self.config.get("devices")

    def getHTPCConfig(self):
        if self.config.get("htpc") is not None:
            return self.config["htpc"].get("enabled"), self.config["htpc"].get("binary")
        else:
            return False, None

    def getMounts(self):
        if self.config["container"].get("mounts") is not None:
            return self.config["container"]["mounts"]
        else:
            return None

    def getPlatform(self):
        return self.config.get("platform")

    def getPlatformConfig(self):
        return self.config.get("platform_options", default={})

    def getScripts(self):
        return self.config.get("scripts")

    def setMount(self, mount):
        try:
            self.config["container"]["mounts"].update(mount)
        except:
            print("Incorrect value passed to setMount. Check your configuration.")
            print("Exception: %s" % e)

    def setEnvironment(self, env):
        if self.config["container"].get("environment") is None:
            self.config["container"]["environment"] = {}
        try:
            self.config["container"]["environment"].update(env)
            return True
        except Exception as e:
            print("Incorrect value passed to setEnvironment. Check your configuration.")
            print("Attempted value: %s" % env)
            print("Exception: %s" % e)

    def setEntryPoint(self, entrypoint):
        self.config["container"]["entrypoint"] = entrypoint
    
    def setWorkingDir(self, working_dir):
        self.config["container"]["workingDir"] = working_dir

    def setPreRunScript(self, script):
        self.config["scripts"]["pre_run"] = script

    def setRunningExecutable(self, executable):
        self.config["appconfig"]["running_executable"] = executable

    def printConfig(self, config):
        # For debug purposes. Pretty prints the entire loaded config
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(self.config)

