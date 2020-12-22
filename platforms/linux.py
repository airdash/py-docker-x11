import os
import threading
import time
import shutil
from util import user
from util import proxysocket 

def create_socket(work_dir, socket_name, target_path, container_uid, container_gid):

    socket = proxysocket.ProxySocket(os.path.join(work_dir, socket_name), target_path, container_uid, container_gid)
    socket_thread = threading.Thread(target = socket.listen)
    socket_thread.start()
    return socket

def configure(config):

    app_config = config.safe_get("appconfig")
    container_config = config.safe_get("container")

    profile_directory = config.safe_get("profileDir")
    app_dir = config.safe_get("appDirs")["linux"]

    if config.get("app_name_override"):
        current_app_name = config.safe_get("app_name_override")
    else:
        current_app_name = app_config["app_name"]
    
    if config.get("platform_alias"):
        current_platform_name = config.safe_get("platform_alias")
    else:
        current_platform_name = config.safe_get("platform")

    platform_app_dir = os.path.join(current_platform_name, current_app_name)

    container_uid = config.get("container", "user_uid")
    container_gid = config.get("container", "user_gid")

    if os.path.exists(os.path.join(os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "default"))) and config.get("subprofileUser"):
        default_profile_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "default")
        default_state_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "default", "state")
    elif os.path.exists(os.path.join(os.path.join(profile_directory, "default", current_platform_name, "default"))):
        default_profile_directory = os.path.join(os.path.join(profile_directory, "default", current_platform_name, "default"))
        default_state_directory = os.path.join(os.path.join(profile_directory, "default", current_platform_name, "default, ""state"))
    elif os.path.exists(os.path.join(os.path.join(profile_directory, "default", platform_app_dir))):
        default_profile_directory = os.path.join(os.path.join(profile_directory, "default", platform_app_dir))
        default_state_directory = os.path.join(os.path.join(profile_directory, "default", platform_app_dir, "state"))
    else:
        default_profile_directory = None
        default_state_directory = None

    if not container_uid:
        container_uid = 0
    if not container_gid:
        container_gid = 0

    if app_config.get("override_image_entrypoint") == True:
        entrypoint = [ os.path.join(app_config["internal_app_dir"], app_config["exepath"], app_config["executable"]), 
                       app_config["programArgs"] ]

    if config.get("appconfig", "app_data_src") == "mount".lower():
        if config.get("appconfig", "external_app_dir"):
            app_mount_src = config.get("appconfig", "external_app_dir")
        else:
            app_mount_src = os.path.join(app_dir, app_config["app_name"])

        app_mount_dst = app_config["internal_app_dir"]

        config.setMount({app_mount_src : app_mount_dst})

    if config.get("appconfig", "internal_state_dir") and not config.get("no_state"):
        if config.get("subprofileUser"):
            user_profile_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, config.safe_get("subprofileUser"))
            user_state_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, config.safe_get("subprofileUser"), "state")
        else:
            user_profile_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir)
            user_state_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "state")

        if not os.path.exists(user_profile_directory):
            if default_profile_directory:
                shutil.copytree(default_profile_directory, user_profile_directory, symlinks=True)
                if not os.path.exists(os.path.join(user_profile_directory, "state")):
                    os.makedirs(os.path.join(user_profile_directory, "state"))
                user.chown(user_profile_directory, container_uid, container_gid, recursive=True, no_root_chown=True)
            else:
                os.makedirs(os.path.join(user_profile_directory, "state"))
                user.chown(user_profile_directory, container_uid, container_gid, recursive=True, no_root_chown=True)

        elif os.path.exists(user_profile_directory) and not os.path.exists(user_state_directory):
            if os.path.exists(os.path.join(default_state_directory)):
                shutil.copytree(default_state_directory, user_state_directory, symlinks=True)
                user.chown(user_state_directory, container_uid, container_gid, recursive=True)
            else:
                os.makedirs(user_state_directory)
                user.chown(user_state_directory, container_uid, container_gid)

        config.setMount({user_state_directory : { "bind" : app_config["internal_state_dir"], "mode" : "rw" }})
    
    print("[DEBUG] - About to check for socket bind options")
    print("[DEBUG] - %s" % config.get("platform_options"))
    print("[DEBUG] - %s" % config.get("platform_options", "socket_binds"))

    # This should go into configuration
    if config.get("workDir") is not None:
        work_dir = config.get("workDir")
    else:
        work_dir = os.getenv("HOME")

    sockets = []

    if config.get("platform_options", "socket_binds"):
        print("[DEBUG] - Got passed the platform options / socket binds check")

        if config.get("platform_options", "socket_binds", "docker"):
            print("[DEBUG] - Setting up Docker socket")
            sockets.append(create_socket(work_dir, "docker-socket", "/var/run/docker.sock", 
                                         container_uid, container_gid))
            config.setMount({ os.path.join(work_dir, "docker-socket"): { "bind" : "/var/run/docker.sock", 
                              "mode" : "rw" }})

        if config.get("platform_options", "socket_binds", "system_dbus"):
            print("[DEBUG] - Setting up system dbus socket")
            sockets.append(create_socket(work_dir, "system-dbus-socket", "/run/dbus/system_bus_socket", 
                                         container_uid, container_gid))
            config.setMount({ os.path.join(work_dir, "system-dbus-socket"): { "bind" : "/run/dbus/system_bus_socket", 
                              "mode" : "rw" }})
