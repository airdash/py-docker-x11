import re
import yaml
import os

class Build:
    def __init__(self, app_config_file, args, base_config, client):

        self.app_config_file = app_config_file
        self.args = args
        self.base_config = base_config
        self.client = client

        with open(app_config_file) as f:
            self.raw_jinja = f.read()
            app_config_yaml = re.sub(r".*\{[{%].*\n", "", self.raw_jinja)
            self.app_config = yaml.safe_load(app_config_yaml)

        self.app_config = self.app_config
        self.automatic = self.app_config.get("build", {}).get("automatic", False)
        self.image = self.app_config.get("build", {}).get("image", None)
        self.tag = self.app_config.get("build", {}).get("tag", None)

        self.full_image_name = format("%s:%s" % ( self.image, self.tag))

        if os.path.basename(os.path.dirname(self.app_config_file)) == "configs":
            build_dir = os.path.abspath(os.path.join(os.path.dirname(self.app_config_file), os.pardir))
        else:
            build_dir = os.path.dirname(self.app_config_file)

        dockerfile = self.app_config.get("build", {}).get("dockerfile", None)

        if self.app_config.get("build"):
            if self.app_config["build"].get("dockerfile"):
                dockerfile = os.path.join(build_dir, self.app_config["build"].get("dockerfile"))
            else:
                dockerfile = os.path.join(build_dir, "Dockerfile")
        else:
            dockerfile = os.path.join(build_dir, "Dockerfile")

        self.build_dir = os.path.expanduser(build_dir)
        self.depends_on = []
        self.dockerfile = dockerfile

        if os.path.exists(dockerfile):
            with open(dockerfile) as dockerfile:
                for line in dockerfile:
                    line = line.strip()
                    if line.startswith("FROM"):
                        # Get the dependent image inside of the Dockerfile
                        self.depends_on.append(line.split()[1])
        else:
            pass
            # print("No Dockerfile associated with build %s:%s found, skipping." % (image, tag))

