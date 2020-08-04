import os, sys
import jinja2, yaml
import functools
import collections
import importlib

class YamlReaderError(Exception):
    pass

class Config:
    def __init__(self, args, client):
        base_dir = os.path.join(os.path.expanduser("~"), ".py-docker-x11")
        profile_user = args.profile
        jinja_render_args = { "current_user" : os.getenv("USER"), "profile_user" : profile_user }

        base_config_yamlfile = self._getBaseConfig(base_dir)
        base_config = self._renderConfig(base_config_yamlfile, **jinja_render_args)

        jinja_render_args["container_user"] = base_config["container"]["user"]
        jinja_render_args["profile_dir"] = base_config["profileDir"]

        if args.image is not None:
            image = args.image.split(':')[0]
            try:
                tag = args.image.split(':')[1]
            except IndexError:
                tag = "latest"
        else:
            image = None

        if image is not None and self._getDockerImageAppConfig(client, image, tag):
            app_config = self._renderConfig(self._getDockerImageAppConfig(client, image, tag), **jinja_render_args)
        else:
            app_dir = base_config["appDirs"].get("default", os.path.join(os.path.expanduser("~"), ".py-docker-x11", "apps"))
            app_config_yamlfile = self._getAppConfig(app_dir, args.app, args.platform)
            app_config = self._renderConfig(app_config_yamlfile, **jinja_render_args)
        
        profile_config_yamlfile = self._getProfileConfig(base_config["profileDir"], profile_user, app_config["platform"], 
                                                         app_config["appconfig"]["app_name"])

        if profile_config_yamlfile:
            profile_config = self.renderConfig(self._getProfileConfig(), **jinja_render_args)
        else:
            profile_config = {}


        if profile_config.get("profileUser") is not None and profile_config.get("profileUser") is not profile_user:
            profile_user = self.config["profileUser"]
            self.__init__(self, args.app, args.platform, profile_user)

        self.config = self._mergeConfig(base_config, app_config, profile_config)

        self.config["profileUser"] = profile_user

        # Hack until we have a .set() method and support for --user
        self.config["currentUser"] = os.getenv("USER")

        # Handle special command line arguments
        if args.entrypoint:
            self.config["container"]["entrypoint"] = args.entrypoint

        if args.tty:
            self.config["container"]["tty"] = True

        if args.interactive:
            self.config["container"]["stdin_open"] = True

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
    
    def _getProfileConfig(self, profile_dir, user_profile, platform, app):
        print("Looking for ", os.path.join(profile_dir, user_profile, platform, app, "profile_config.yaml"))
        if os.path.exists(os.path.join(profile_dir, user_profile, platform, app, "profile_config.yaml")):
            return os.path.join(profile_dir, user_profile, platform, app, "profile_config.yaml")
        else:
            return False

    # Returns None for statements made for handling such cases
    def get(self, *args):
        return functools.reduce(lambda curr, arg: curr.get(arg) if curr else None, args, self.config)

    # Raises exception instead of returning None
    def safe_get(self, *args):
        retval = functools.reduce(lambda curr, arg: curr.get(arg) if curr else None, args, self.config)

        if retval is None:
            raise Exception("Failed to get config value! Something is wrong.")
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

    def printConfig(self, config):
        # For debug purposes. Pretty prints the entire loaded config
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(self.config)

