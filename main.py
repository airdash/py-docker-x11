#!/usr/bin/env python3 
import os
import argparse
import pprint
import configuration, supervisor 
import docker

def checkUser(user):
    # TODO: Ensure that the user specified is a user with appropriate subuid/gids, and is running Docker.
    pass

def parseArguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--app", default=None, help="Set the name of the currently running application (and associated state)")
    parser.add_argument("-b", "--baseconfig", help="Specify the base configuration yaml file.")
    parser.add_argument("-c", "--command", help="Override the defined command in the container.")
    parser.add_argument("-d", "--debug", action='store_true', help="Set debug mode.")
    parser.add_argument("-e", "--entrypoint", help="Override the defined entrypoint in the container.")
    parser.add_argument("-i", "--interactive", action='store_true', help="Keep STDIN open for an interactive session.")
    parser.add_argument("--install", action='store_true', help="Implies maintenance. Disables additional mounts and state mount as well.")
    parser.add_argument("-m", "--maintenance", action='store_true', help="Enter container in maintenance mode - changes any R/O mounts to R/W. Use for updating or installing software within a new bind mount")
    parser.add_argument("-n", "--norm", action='store_true', help="Do not remove container after termination.")
    parser.add_argument("--network", default=None, help="Specify the network to connect the container to.")
    parser.add_argument("--no-mount", action='store_true', help="Do not mount auxillary directories.")
    parser.add_argument("--no-state", action='store_true', help="Do not mount user state directory.")
    parser.add_argument("-p", "--profile", default=None, help="Specify the profile to run the program under.")
    parser.add_argument("--platform", default=None, help="Specify the platform that the application runs under")
    parser.add_argument("--profiledir", default=None, help="Specify the directory that profiles are kept under")
    parser.add_argument("-s", "--subprofile", help="Specify the subprofile to run under for applications with subprofiles.")
    parser.add_argument("--socket", action='store_true', help="Specify Docker socket to run container under.")
    parser.add_argument("-t", "--tty", action='store_true', help="Allocate a pseudo-tty for this session.")
    parser.add_argument("-u", "--user", help="Specify the container user to run inside the container.")
    parser.add_argument("-v", "--verbose", action='store_true', help="Set verbose mode.")
    parser.add_argument("-x", "--xpra", action='store_true', help="Run container inside of a new xpra session.")
    parser.add_argument("--x11", action='store_true', help="Run container inside of a new X11 session.")
    parser.add_argument("image", nargs="?", default=None, help="Image + tag to run and import app_config from, if applicable.")
    args, container_args = parser.parse_known_args()

    return args, container_args

def main():

    print("Using docker-py version %s" % docker.version)
    args, container_args = parseArguments()

    if args.socket:
        socket = args.socket
    else:
        socket = 'unix://home/docker/sockets/sandbox/docker.sock'
    # else:
    #     socket = 'unix://var/lib/docker/docker.sock'

    client = docker.APIClient(base_url=socket)
    config = configuration.Config(args, container_args, client)

    if args.debug == True:
        print("Run complete. Below is the complete config.")
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(config)

    for _, dir in config.get("appDirs").items():
        if not os.path.exists(dir):
            print("Making directory %s" % dir)
            os.makedirs(dir)
    if not os.path.exists(config.get("profileDir")):
        os.makedirs(config.get("profileDir"))
    if not os.path.exists(config.get("workDir")):
        os.makedirs(config.get("workDir"))

    print("Spawning new supervisor")
    app = supervisor.Supervisor(config, client)
    print("Running supervisor")
    app.run()

if __name__ == '__main__':
    main()
