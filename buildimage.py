#!/usr/bin/env python3

import docker 
import argparse
import yaml
import os, sys
import re
import glob
import jinja2

class NullUndefined(jinja2.Undefined):
    def __getitem__(self, key):
        return self
    def __getattr_(self, key):
        return self

def getBaseConfig(base_dir):

    # If the yaml's here for some reason, just use it.
    if os.path.exists(os.path.join(os.getcwd(), "base_config.yaml")):
        print("[WARN] Using base_config.yaml in current directory!")
        return os.path.join(os.getcwd(), "base_config.yaml")

    # Else, let's check the user's home directory (where it should be)
    if os.path.exists(os.path.join(os.path.expanduser("~"), ".py-docker-x11", "base_config.yaml")):
        return os.path.join(os.path.expanduser("~"), ".py-docker-x11", "base_config.yaml")
    else:
        return False

def getAppConfig(file):
    with open(file) as jinja_file:
        raw_jinja = jinja_file.read()
    # template = jinja2.Environment(loader=jinja2.FileSystemLoader(os.getcwd()), undefined=NullUndefined)
    # rendered_yaml_file = template.get_template("app_config.yaml").render()

    # This may not be necessary
    app_config_yaml = re.sub(r".*\{[{%].*\n", "", raw_jinja)

    app_config = yaml.load(app_config_yaml, Loader=yaml.SafeLoader)
    return raw_jinja, app_config

def buildImage(client, raw_jinja, app_config, args):
    print(raw_jinja)
    print(app_config)

    pull = False
    nocache = False

    print("args: %s" % args)
    print("args.full: %s" % args.full)
    print("args.pull: %s" % args.pull)
    print("args.nocache: %s" % args.nocache)

    if args.full or args.pull:
        pull = True
    if args.full or args.nocache:
        nocache = True
    
    if app_config["build"].get("dockerfile"):
        dockerfile = app_config["build"].get("dockerfile")
    else:
        dockerfile = "Dockerfile"

    try:
        result = client.build(path=os.getcwd(), labels={"pdx-app-config": raw_jinja}, 
                dockerfile=os.path.join(os.getcwd(), dockerfile),
                tag=app_config["build"]["image"] + ":" + app_config["build"]["tag"],
                pull=pull, nocache=nocache, decode=True) 

        for message in result:
            if 'stream' in message:
                for line in message['stream'].splitlines():
                    print(line)
        return True
    except Exception as e:
        print(e)
        print("Failure encountered during build process")
        return False

def pushImage(client, base_config, app_config, push):
    if push == True or base_config.get("build").get("always_push") == True or app_config.get("build").get("always_push") == True:
        print("Pushing image to %s:%s" % (app_config["build"]["image"], app_config["build"]["tag"]) )
        try:
            result = client.push(repository=app_config["build"]["image"], tag=app_config["build"]["tag"], decode=True)
            print("Build successfully pushed.")
            return True
        except:
            print("Push failed! Check your configs or your destination repository.")
            return False

def main(args):

    base_config = {}
    base_dir = os.path.join(os.path.expanduser("~"), ".py-docker-x11")
    client = docker.APIClient(base_url='unix://home/docker/sockets/sandbox/docker.sock')

    if getBaseConfig(base_dir):
        base_config_yamlfile = getBaseConfig(base_dir)
        with open(base_config_yamlfile) as yaml_file:
            base_config_yaml = yaml_file.read()
        base_config = yaml.load(base_config_yaml, Loader=yaml.SafeLoader)

    if glob.glob("./configs/*.yaml"):
        for config in glob.glob("./configs/*.yaml"):
            raw_jinja, app_config = getAppConfig(config)
            if buildImage(client, raw_jinja, app_config, args):
                pushImage(client, base_config, app_config, args.push)

    elif os.path.exists("app_config.yaml"):
        raw_jinja, app_config = getAppConfig("app_config.yaml")
        if buildImage(client, raw_jinja, app_config, args):
            pushImage(client, base_config, app_config, args.push)

    else:
        print("app_config.yaml or config directory does not exist in the current directory. Exiting.")
        sys.exit(1)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action='store_true', default=False, help="Enables pull and nocache")
    parser.add_argument("--nocache", action='store_true', default=False, help="Do not use cache during build")
    parser.add_argument("--pull", action='store_true', default=False, help="Pull image before build")
    parser.add_argument("--push", action='store_true', help="Push image after build")
    args = parser.parse_args()

    main(args)
