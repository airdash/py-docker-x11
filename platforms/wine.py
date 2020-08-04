import os
import shutil

def configure(config):
    LD_PRELOAD = []

    app_config = config.safe_get("appconfig")
    container_config = config.safe_get("container")
    docker_config = config.safe_get("docker")

    profile_directory = config.safe_get("profileDir")
    platform_app_dir = os.path.join(config.safe_get("platform"), app_config["app_name"])

    default_wine_directory = os.path.join(os.path.join(profile_directory, "default", platform_app_dir, "wine-base"))

    if app_config.get("override_image_entrypoint") == True:
        entrypoint = [ os.path.join(app_config["internal_app_dir"], app_config["exepath"], app_config["executable"]), 
                       app_config["programArgs"] ]

    if config.get("platform_options", "per_profile_wine_base"):
        if app_config.get("use_subprofiles") == True:
            user_wine_directory = os.path.join(profile_directory, config.safe_get("currentUser"), platform_app_dir, config.safe_get("profileUser"), "wine-base")
    
        else:
            user_wine_directory = os.path.join(profile_directory, config.safe_get("profileUser"), platform_app_dir, "wine-base")
    
        if not os.path.exists(user_wine_directory):
            if os.path.exists(default_wine_directory):
                shutil.copytree(default_wine_directory, user_wine_directory)
            else:
                os.makedirs(os.path.join(user_wine_directory, "drive_c"))
                os.chown(user_wine_directory, config["docker"]["userSubUID"], config["docker"]["groupSubUID"])
                print("First run for this profile! We will be running wineboot -u.")
                container_config["entrypoint"] = [ os.path.join(config["platform_options"]["wineDir"], "wineboot"), "-u" ]

    app_dir = config.safe_get("appDirs")["windows"]
    if config.get("appconfig", "app_data_src") == "mount".lower():
        if config.get("platform_options", "per_profile_wine_base"):
            if config.get("platform_options", "protect_wine_base"):
                config.setMount({user_wine_directory : 
                                { "bind" : app_config["internal_app_dir"],
                                  "mode" : "ro" }})
            else:
                config.setMount({user_wine_directory : 
                                { "bind" : app_config["internal_app_dir"],
                                  "mode" : "rw" }})

            wine_drive_c_mount = os.path.join(app_dir, app_config["app_name"], "drive_c")

            if config.get("platform_options", "protect_drive_c"):
                config.setMount({ wine_drive_c_mount : 
                                { "bind" : os.path.join(app_config["internal_app_dir"], "drive_c"),
                                  "mode" : "ro" }})
            else:
                config.setMount({ wine_drive_c_mount : 
                                { "bind" : os.path.join(app_config["internal_app_dir"], "drive_c"),
                                  "mode" : "rw" }})
            
        else:
            wine_mount = os.path.join(app_dir, app_config["app_name"])

            if config.get("platform_options", "protect_wine_dir"):
                config.setMount({ wine_mount :
                                { "bind" : app_config["internal_app_dir"],
                                  "mode" : "ro" }})
            else:
                config.setMount({ wine_mount :
                                { "bind" : app_config["internal_app_dir"],
                                  "mode" : "rw" }})

            config.setMount({ os.path.expanduser("~/.cache/winetricks") :
                            { "bind" : os.path.join("/home/sandbox/.cache/winetricks"), 
                              "mode" : "ro" }})

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
        
    if not config.get("platform_options", "pba") is True:
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

    return config
