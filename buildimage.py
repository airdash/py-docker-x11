#!/usr/bin/env python3

import docker 
import argparse
import yaml
import os, sys
import re
from build.dag import DAG
from build.build import Build
from build.builder import Builder

def find_yaml_files(path, recurse=True):
    found_files = []
    if recurse:
        for root, dirs, files in os.walk(path):
            for file in files:
                if file == "app_config.yaml" or file == "app_config.yml":
                    found_files.append(os.path.join(root, file))
                elif file.endswith((".yaml", ".yml")) and "config" in root:
                    found_files.append(os.path.join(root, file))
    else:
        if os.path.exists(os.path.join(path, "app_config.yaml")):
            found_files.append(os.path.join(path, "app_config.yaml"))
        elif os.path.exists(os.path.join(path, "app_config.yml")):
            found_files.append(os.path.join(path, "app_config.yml"))

    return found_files

def getBaseConfig():

    # Check if the base_config.yaml file exists in the current working directory
    cwd = os.getcwd()
    base_config_path = None
    cwd_config_path = os.path.join(cwd, "base_config.yaml")
    if os.path.exists(cwd_config_path):
        base_config_path = cwd_config_path

    else:
        # Check if the base_config.yaml file exists in the user's home directory
        home_dir = os.path.expanduser("~")
        home_config_path = os.path.join(home_dir, ".py-docker-x11", "base_config.yaml")
        if os.path.exists(home_config_path):
            base_config_path = home_config_path

    if base_config_path:
        with open(base_config_path) as yaml_file:
            base_config_yaml = yaml_file.read()
        return yaml.load(base_config_yaml, Loader=yaml.SafeLoader)
    else:
        print("No base config found!")
        sys.exit(1)

def parseArgs():

    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action='store_true', default=False, help="Run all automatic builds")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Only show builds that would have occurred.")
    parser.add_argument("--force", action='store_true', default=False, help="Force build even if images are too new")
    parser.add_argument("--full", action='store_true', default=False, help="Enables pull and nocache")
    parser.add_argument("--nocache", action='store_true', default=False, help="Do not use cache during build")
    parser.add_argument("--pull", action='store_true', default=False, help="Pull image before build")
    parser.add_argument("--push", action='store_true', help="Push image after build")
    parser.add_argument("--update", action='store_true', help="Run update builds")
    return parser.parse_args()

def main(args):

    base_config = getBaseConfig()
    
    if not re.match(r"^unix://", base_config["docker_socket"]):
        base_config["docker_socket"] = "unix://" + base_config["docker_socket"]
    
    client = docker.APIClient(base_config["docker_socket"])
    cwd = os.getcwd()

    build_type = base_config.get("build_type")
    print("Build Type is %s" % build_type)

    if build_type == "local":
        dag = DAG()

        if args.auto:
            app_config_files = find_yaml_files(os.path.expanduser(base_config["build"]["build_dir"]))
        else:
            app_config_files = find_yaml_files(cwd, recurse=False)

            if os.path.exists(os.path.join(cwd, "configs")):
                found_yaml_files = find_yaml_files(os.path.join(cwd, "configs"))
                app_config_files.extend(find_yaml_files(os.path.join(cwd, "configs")))
        
        if app_config_files:
            builds = []
            for app_config_file in app_config_files:
                builds.append(Build(app_config_file, args, base_config, client))

            for build in builds:
                if args.auto and not build.automatic:
                    continue
                for dependency in build.depends_on:
                    dag.add_edge(dependency, build.full_image_name, build)

            for build in dag.topological_sort():
                print("Building %s" % build.app_config_file)
                if not args.dry_run:
                    builder = Builder(args, base_config, build, client)
                    builder.run_build()

if __name__ == '__main__':
    main(parseArgs())
