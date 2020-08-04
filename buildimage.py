#!/usr/bin/env python3

import docker 
import yaml
import os, sys
import re

def main():
    client = docker.APIClient()

    if os.path.exists("app_config.yaml"):
        with open("app_config.yaml") as yaml_file:
            app_config_jinja = yaml_file.read()

        app_config_yaml = re.sub(r".*\{[{%].*\n", "", app_config_jinja)
        app_config = yaml.load(app_config_yaml, Loader=yaml.SafeLoader)
    else:
        print("app_config.yaml does not exist in the current directory. Exiting.")
        sys.exit(1)

    result = [ line for line in client.build(path=os.getcwd(), labels={"pdx-app-config": app_config_jinja}, 
            dockerfile=os.path.join(os.getcwd(), "Dockerfile"),
            tag=app_config["build"]["image"] + ":" + app_config["build"]["tag"],
            pull=True) ]

    print(result)

if __name__ == '__main__':
    main()
