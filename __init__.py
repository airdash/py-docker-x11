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
    parser.add_argument("-a", "--app", default=None,
                        help="Specify the app to run. Defaults to the current working directory.")
    parser.add_argument("-b", "--baseconfig", help="Specify the base configuration yaml file.")
    parser.add_argument("-c", "--command", help="Override the defined command in the container.")
    parser.add_argument("-d", "--debug", action='store_true', help="Set debug mode.")
    parser.add_argument("-e", "--entrypoint", help="Override the defined entrypoint in the container.")
    parser.add_argument("-i", "--interactive", action='store_true', help="Keep STDIN open for an interactive session.")
    parser.add_argument("-p", "--profile", default=os.getenv("USER"),
                        help="Specify the profile to run the program under.")
    parser.add_argument("--platform", default=None, help="Specify the platform that the application runs under")
    parser.add_argument("--profiledir", default=None, help="Specify the directory that profiles are kept under")
    parser.add_argument("-s", "--sandbox-user", help="Specify the external sandbox user to run the container under.")
    parser.add_argument("-t", "--tty", action='store_true', help="Allocate a pseudo-tty for this session.")
    parser.add_argument("-u", "--user", help="Specify the external user to run the container under.")
    parser.add_argument("-v", "--verbose", action='store_true', help="Set verbose mode.")
    parser.add_argument("-x", "--x11", action='store_true', help="Run container inside of a new X11 session.")
    parser.add_argument("image", nargs="?", default=None, help="Image + tag to run and import app_config from, if applicable.")
    args = parser.parse_args()

    return args

def main():

    args = parseArguments()
    client = docker.APIClient()
    config = configuration.Config(args, client)

    if args.debug == True:
        print("Run complete. Below is the complete config.")
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(config)

    print("Spawning new supervisor")
    app = supervisor.Supervisor(config, client)
    print("Running supervisor")
    app.run()

if __name__ == '__main__':
    main()
