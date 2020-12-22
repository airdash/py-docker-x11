import os
import sys
import shutil
from util import user
from pathlib import Path

def convert_wine_to_profile(application_dir, user_wine_directory):
    for target in ["dosdevices", "system.reg", "userdef.reg", "user.reg", ".update-timestamp"]:
        print("Checking for %s" % os.path.join(application_dir, target))
        print("Target is %s" % os.path.join(user_wine_directory, target))
        full_target = os.path.join(application_dir, target)
        if os.path.exists(full_target):
            if os.path.isdir(full_target):
                shutil.copytree(full_target, os.path.join(user_wine_directory, target), symlinks=True)
            elif os.path.isfile(full_target):
                shutil.copy2(full_target, os.path.join(user_wine_directory, target))
        else:
            print("Something went wrong converting the wine profile, please check the user wine profile directory")
            break

def configure(config):
    LD_PRELOAD = []

    app_config = config.safe_get("appconfig")
    app_dir = config.safe_get("appDirs")["windows"]
    container_config = config.safe_get("container")
    profile_directory = config.safe_get("profileDir")

    if config.get("app_name_override"):
        current_app_name = config.safe_get("app_name_override")
    else:
        current_app_name = app_config["app_name"]

    if config.get("platform_alias"):
        current_platform_name = config.safe_get("platform_alias")
    else:
        current_platform_name = config.safe_get("platform")
    
    platform_app_dir = os.path.join(current_platform_name, current_app_name)

    if os.path.exists(os.path.join(os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "default", "wine-base"))) and config.get("subprofileUser"):
        default_wine_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "default", "wine-base")
    elif os.path.exists(os.path.join(os.path.join(profile_directory, "default", current_platform_name, "default", "wine-base"))):
        default_wine_directory = os.path.join(os.path.join(profile_directory, "default", current_platform_name, "default", "wine-base"))
    elif os.path.exists(os.path.join(os.path.join(profile_directory, "default", platform_app_dir, "wine-base"))):
        default_wine_directory = os.path.join(os.path.join(profile_directory, "default", platform_app_dir, "wine-base"))
    else:
        default_wine_directory = None

    if os.path.exists(os.path.join(os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "default"))) and config.get("subprofileUser"):
        default_profile_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "default")
    elif os.path.exists(os.path.join(os.path.join(profile_directory, "default", current_platform_name, "default"))):
        default_profile_directory = os.path.join(os.path.join(profile_directory, "default", current_platform_name, "default"))
    elif os.path.exists(os.path.join(os.path.join(profile_directory, "default", platform_app_dir))):
        default_profile_directory = os.path.join(os.path.join(profile_directory, "default", platform_app_dir))
    else:
        default_profile_directory = None

    print("default_wine_directory is %s" % default_wine_directory)
    print("default_profile_directory is %s" % default_profile_directory)

    container_user = config.get("container", "user")
    container_uid = config.get("container", "user_uid")
    print("[DEBUG] - container_uid is %d" % container_uid)
    container_gid = config.get("container", "user_gid")
    print("[DEBUG] - container_gid is %d" % container_gid)

    if not container_uid:
        container_uid = 0
    if not container_gid:
        container_gid = 0

    if app_config.get("override_image_entrypoint") == True:
        entrypoint = [ os.path.join(app_config["internal_app_dir"], app_config["exepath"], app_config["executable"]), 
                       app_config["programArgs"] ]

    if config.get("platform_options", "per_profile_wine_base"):
        if config.get("subprofileUser"):
            user_profile_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, config.safe_get("subprofileUser"))
            user_wine_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, config.safe_get("subprofileUser"), "wine-base")
        else:
            user_profile_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir)
            user_wine_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "wine-base")
    
        if not os.path.exists(user_wine_directory):
            if default_profile_directory and os.path.exists(default_profile_directory) and not os.path.exists(user_profile_directory) and os.path.exists(os.path.join(default_profile_directory, "wine-base")):
                print("[DEBUG] - Not copying default wine directory from default wine directory as directory in default profile exists.")
            elif default_wine_directory:
                print("[DEBUG] - Copying default wine directory to user wine directory for initial setup")
                shutil.copytree(default_wine_directory, user_wine_directory, symlinks=True)
                user.chown(default_wine_directory, user_wine_directory, recursive=True)
            else:
                print("[DEBUG] - Converting wine directory to new profile")
                os.makedirs(user_wine_directory)
                convert_wine_to_profile(os.path.join(app_dir, app_config["app_name"]), user_wine_directory)
                user.chown(user_wine_directory, container_uid, container_gid, recursive=True)

    if config.get("appconfig", "app_data_src") == "mount".lower():
        if config.get("platform_options", "per_profile_wine_base") and not config.get("install"):
            if config.get("platform_options", "protect_wine_base") and not config.get("maintenance"):
                config.setMount({user_wine_directory : 
                                { "bind" : app_config["internal_app_dir"],
                                  "mode" : "ro" }})
            else:
                config.setMount({user_wine_directory : 
                                { "bind" : app_config["internal_app_dir"],
                                  "mode" : "rw" }})

            if config.get("appconfig", "external_app_dir"):
                wine_drive_c_mount = os.path.join(config.get("appconfig", "external_app_dir"), "drive_c")
            else:
                wine_drive_c_mount = os.path.join(app_dir, app_config["app_name"], "drive_c")

            if config.get("platform_options", "protect_drive_c") and not config.get("maintenance"):
                config.setMount({ wine_drive_c_mount : 
                                { "bind" : os.path.join(app_config["internal_app_dir"], "drive_c"),
                                  "mode" : "ro" }})
            else:
                config.setMount({ wine_drive_c_mount : 
                                { "bind" : os.path.join(app_config["internal_app_dir"], "drive_c"),
                                  "mode" : "rw" }})
            
        else:
            if config.get("appconfig", "external_app_dir"):
                wine_mount = os.path.join(config.get("appconfig", "external_app_dir"))
            else:
                wine_mount = os.path.join(app_dir, app_config["app_name"])

            print("[DEBUG] wine_mount is %s" % wine_mount)

            if config.get("platform_options", "protect_wine_dir") and not config.get("maintenace"):
                config.setMount({ wine_mount :
                                { "bind" : app_config["internal_app_dir"],
                                  "mode" : "ro" }})
            else:
                config.setMount({ wine_mount :
                                { "bind" : app_config["internal_app_dir"],
                                  "mode" : "rw" }})

    if config.get("platform_options", "winetricks_dir"):
        config.setMount({ os.path.expanduser(config.get("platform_options", "winetricks_dir")) :
           { "bind" : os.path.join("/home", container_user, ".cache/winetricks"), "mode" : "rw" }})

    if config.get("maintenance"):
        if config.get("maintenance_dir"):
            config.setMount({ config.get("maintenance_dir") : { "bind" : "/maintenance", "mode": "ro" }})

    if config.get("appconfig", "internal_state_dir") and not config.get("install"):
        if config.get("appconfig", "external_app_dir"):
            current_app_dir = config.get("appconfig", "external_app_dir")
        else:
            current_app_dir = os.path.join(app_dir, app_config["app_name"])

        print("[DEBUG] Container entrypoint is %s" % config.get("container", "entrypoint"))
        print("[DEBUG} internal_state_dir is %s" % app_config["internal_state_dir"])

        if app_config["internal_state_dir"].find("drive_c/users/" + container_user) != -1 and not os.path.exists(os.path.join(current_app_dir, "drive_c", "users", container_user)) and config.get("container", "entrypoint") is None and not os.path.exists(os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir,  container_user + ".generated")):
            print("[WARN] First WINE run for this container user! We will be running wineboot -u via the pre_run script for sanity.")
            # Try to create the internal state dir, too, otherwise we end up with permissions errors
            # config.setEntryPoint([os.path.join(str(config.get("platform_options", "wineDir") or ''), "wineboot"), "-u", '&&', 'mkdir', '-p', app_config["internal_state_dir"]])
            # config.setEntryPoint([os.path.join(str(config.get("platform_options", "wineDir") or ''), "wineboot"), "-u"])
            config.setPreRunScript(os.path.join(str(config.get("platform_options", "wineDir") or ''), "wine") + " wineboot -u && mkdir -p \"" + app_config["internal_state_dir"] + "\"")
            config.setEntryPoint(["bash", "-c", "${HOME}/pre_run.sh"])
            config.setRunningExecutable("bash")

            try:
                print("[DEBUG] Creating path %s so we don't run this twice..." % os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir,  container_user + ".generated"))
                genpath = Path(os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir,  container_user + ".generated"))
                genpath.touch()
            except exception as e:
                print("[ERROR] Something went wrong while trying to set the wineboot marker: %s" % e)

#        elif app_config["internal_state_dir"].find("drive_c/users/" + container_user) != -1 and ( os.path.exists(os.path.join(current_app_dir, "drive_c", "users", container_user)) or os.path.exists(os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir,  container_user + ".generated"))) and not os.path.exists(os.path.join(app_config["internal_app_dir"], re.search("drive_c/users/.*", internal_state_dir)[0])):
#            print("[WARN] === Creating state directory for internal_state_dir inside WINE user profile, this probably won't work and you'll need to create it manually! ===")
#            print("[DEBUG] Making dir %s" % os.path.join(app_config["internal_app_dir"], re.search("drive_c/users/.*", internal_state_dir)[0]))
#            os.makedirs(os.path.join(app_config["internal_app_dir"], re.search("drive_c/users/.*", internal_state_dir)[0]))
#            user.chown(os.path.join(app_config["internal_app_dir"], re.search("drive_c/users/.*", internal_state_dir)[0]), container_uid, container_gid)
        else:
            if config.get("subprofileUser"):
                user_profile_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, config.safe_get("subprofileUser"))
                user_state_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, config.safe_get("subprofileUser"), "state")
                print("[DEBUG] - use_subprofiles is enabled, user state directory is %s" % user_state_directory)
            else:
                user_profile_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir)
                user_state_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "state")
                print("[DEBUG] - use_subprofiles is disabled, user state directory is %s" % user_state_directory)

            if not os.path.exists(user_profile_directory):
                if default_profile_directory:
                    print("[DEBUG] - Creating new user profile directory from default")
                    shutil.copytree(default_profile_directory, user_profile_directory, symlinks=True)
                    if not os.path.exists(os.path.join(user_profile_directory, "state")):
                        os.makedirs(os.path.join(user_profile_directory, "state"))
                    user.chown(user_profile_directory, container_uid, container_gid, recursive=True)
                else:
                    print("[DEBUG] - Creating new user profile from scratch!")
                    os.makedirs(os.path.join(user_profile_directory, "state"))
                    user.chown(user_profile_directory, container_uid, container_gid, recursive=True)
    
            elif os.path.exists(user_profile_directory) and not os.path.exists(user_state_directory):
                if default_profile_directory and os.path.exists(os.path.join(default_profile_directory, "state")):
                    print("[DEBUG] - Copying state into existing user directory")
                    shutil.copytree(default_state_directory, user_state_directory, symlinks=True)
                    user.chown(user_state_directory, container_uid, container_gid, recursive=True)
                else:
                    print("[DEBUG] - Creating new state in existing user directory")
                    os.makedirs(user_state_directory)
                    user.chown(user_state_directory, container_uid, container_gid)

            if not config.get("no_state"):
                config.setMount({ user_state_directory : app_config["internal_state_dir"]})

    if config.get("platform_options", "debug") is True:
    # Cribbing proton options
        config.setEnvironment({ "WINEDEBUG" : "+timestamp,+pid,+tid,+seh,+debugstr,+loaddll,+mscoree" })
        config.setEnvironment({ "DXVK_LOG_LEVEL" : "info" })
        config.setEnvironment({ "VKD3D_DEBUG" : "warn" })
        config.setEnvironment({ "WINE_MONO_TRACE" : "E:System.NotImplementedException" })
    else:
        config.setEnvironment({ "WINEDEBUG" : "-all" })
        config.setEnvironment({ "DXVK_LOG_LEVEL" : "none" })
        config.setEnvironment({ "VKD3D_DEBUG" : "none" })

    if config.get("platform_options", "esync") is True:
        config.setEnvironment({ "WINEESYNC" : 1 })
    else:
        config.setEnvironment({ "WINEESYNC" : 0 })

    # if config["platform_options"]["koku_hack"]:
    #     LD_PRELOAD.append(os.path.join(config["appconfig"]["internal_app_dir"], "koku-xinput.wine.so"))
        
    if config.get("platform_options", "pba") is True:
        config.setEnvironment({ "PBA_DISABLE" : 0 })
        config.setEnvironment({ "PBA_ENABLE" : 1 })
    else:
        config.setEnvironment({ "PBA_DISABLE" : 1 })
        config.setEnvironment({ "PBA_ENABLE" : 0 })
        
    if config.get("container", "workingDir") is not None:
        config.setWorkingDir(os.path.join(config["appconfig"]["internal_app_dir"], config["appconfig"]["exepath"]))

    if app_config.get("override_image_entrypoint") is True:
        # This is basically a hack in case the program in question absolutely won't cooperate.
        if app_config["wrapper"]:
            config.setEntryPoint([ entrypoint ])
        else:
            config.setEntryPoint([ os.path.join(config["platform_options"]["wineDir"], "wine"), entrypoint ])

    if config.get("platform_options", "wine_shm_hack") is True:
        config.setEnvironment({"LD_PRELOAD" : str(config.get("container", "environment", "LD_PRELOAD") or '') + " " + config.get("platform_options", "wine_shm_hack_32bit_path") + " " + config.get("platform_options","wine_shm_hack_64bit_path")})
        print("Set LD_PRELOAD to %s" % config.get("container","environment", "LD_PRELOAD"))
    return config
