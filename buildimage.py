#!/usr/bin/env python3

import docker 
import argparse
import yaml
import os, sys
import re
import subprocess
import glob
import jinja2
import shutil
import hashlib
import build 
from io import BytesIO

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

def pullVideoDriver(driver_cache_path, docker_build_path):
    result = subprocess.check_output(["lsmod"]).decode('utf-8').split()
    if 'nvidia' in result:
        from build import nvidia_driver
        nvidia_driver.pull(driver_cache_path, docker_build_path)
    else:
        print("No driver found for video card! Continuing.")

def getAppConfig(file):
    with open(file) as jinja_file:
        raw_jinja = jinja_file.read()
    # template = jinja2.Environment(loader=jinja2.FileSystemLoader(os.getcwd()), undefined=NullUndefined)
    # rendered_yaml_file = template.get_template("app_config.yaml").render()

    # This may not be necessary
    app_config_yaml = re.sub(r".*\{[{%].*\n", "", raw_jinja)

    app_config = yaml.load(app_config_yaml, Loader=yaml.SafeLoader)
    return raw_jinja, app_config

    modinfo_output = subprocess.check_output(["modinfo", "nvidia"]).decode('utf-8').splitlines()
    
def buildImage(client, raw_jinja, base_config, app_config, args):
    # print(raw_jinja)
    # print(app_config)

    pull = False
    nocache = True
    inline_dockerfile = None

    print("args: %s" % args)
    print("args.full: %s" % args.full)
    print("args.pull: %s" % args.pull)
    print("args.nocache: %s" % args.nocache)

    if args.full or args.pull:
        pull = True
    if args.full or args.nocache:
        nocache = True

    image = app_config["build"]["image"] 
    tag = app_config["build"]["tag"]
    
    always_full_update = app_config["build"].get("always_full_update")
    image_exists_locally = client.images(name=image + ":" + tag)
    image_exists_remotely = False

    if not image_exists_locally and app_config["build"].get("remote"):
        print("[WARN] Could not find image locally, attempting pull...")

        try:
    	    image_exists_remotely = client.pull(image, tag=tag)
        except:
            print("[WARN] Could not find image remotely.")

    if args.update and ( image_exists_locally or image_exists_remotely ) and not always_full_update:
        if app_config["build"].get("dockerfile_update_file"):
            dockerfile = app_config["build"].get("dockerfile_update_file")

        # Check to make sure someone didn't accidentally give a file or something else in dockerfile_update
        # Also, build Dockerfile in file-like object

        elif app_config["build"].get("dockerfile_update") and isinstance(app_config["build"].get("dockerfile_update"), list):
            from_found = False
            dockerfile_update = app_config["build"].get("dockerfile_update")
            print(dockerfile_update)

            for line in range(len(dockerfile_update)):
                if not re.match("FROM|RUN|COPY|ADD|ENV|USER", dockerfile_update[line]):
                    dockerfile_update[line] = "RUN " + dockerfile_update[line]
                elif re.match("FROM", dockerfile_update[line]):
                    from_found = True

            if not from_found:
                dockerfile_update = [ "FROM " + image + ":" + tag + "\n" ] + dockerfile_update
                    
            print(dockerfile_update)
            print("\n".join(dockerfile_update))
            inline_dockerfile = BytesIO(bytes("\n".join(dockerfile_update), 'utf-8'))
            
        elif os.path.exists("Dockerfile-update"):
            dockerfile = "Dockerfile-update"
        else:
            dockerfile = "Dockerfile"
    else:
        if app_config["build"].get("dockerfile"):
            dockerfile = app_config["build"].get("dockerfile")
        else:
            dockerfile = "Dockerfile"

    if app_config["build"].get("install_gpu_driver") == True:
        driver_cache_path = os.path.expanduser(base_config["appDirs"].get("driver_cache"))
        docker_build_path = os.getcwd()
        pullVideoDriver(driver_cache_path, docker_build_path)

    try:
        if inline_dockerfile:
            result = client.build(path=os.getcwd(), labels={"pdx-app-config": raw_jinja}, 
                    fileobj=inline_dockerfile, tag=app_config["build"]["image"] + ":" + app_config["build"]["tag"],
                    pull=pull, nocache=nocache, decode=True) 
        else:
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
    client = docker.APIClient(base_url='unix://home/docker/sandbox/socket/docker.sock')

    if getBaseConfig(base_dir):
        base_config_yamlfile = getBaseConfig(base_dir)
        with open(base_config_yamlfile) as yaml_file:
            base_config_yaml = yaml_file.read()
        base_config = yaml.load(base_config_yaml, Loader=yaml.SafeLoader)

    if glob.glob("./configs/*.yaml"):
        for config in glob.glob("./configs/*.yaml"):
            raw_jinja, app_config = getAppConfig(config)
            if buildImage(client, raw_jinja, base_config, app_config, args):
                pushImage(client, base_config, app_config, args.push)

    elif os.path.exists("app_config.yaml"):
        raw_jinja, app_config = getAppConfig("app_config.yaml")
        if buildImage(client, raw_jinja, base_config, app_config, args):
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
    parser.add_argument("--update", action='store_true', help="Run update builds")
    args = parser.parse_args()

    main(args)
