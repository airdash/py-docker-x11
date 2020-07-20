import os
import shutil

def configure(config):
    LD_PRELOAD = []

    default_wine_directory = os.path.join(os.path.join(config["profile_directory"], "default", config["platform"], config["appconfig"]["appname"],
                                                       "wine-base"))

    if config["appconfig"].get("use_subprofiles") == True:
        user_wine_directory = os.path.join(config["profile_directory"], config["currentUser"], config["platform"], config["appconfig"]["appname"], 
                                           config["userProfile"], "wine-base")
    else:
        user_wine_directory = os.path.join(config["profile_directory"], config["userProfile"], config["platform"], config["appconfig"]["appname"], 
                                           "wine-base")

    if not os.path.exists(user_wine_directory):
        if os.path.exists(default_wine_directory):
            shutil.copytree(default_wine_directory, user_wine_directory)
        else:
            os.makedirs(os.path.join(user_wine_directory, "drive_c"))
            os.chown(user_wine_directory, config["docker"]["userSubUID"], config["docker"]["groupSubUID"])
            print("First run for this profile! We will be running wineboot -u.")
            config["container"]["entrypoint"] = [ os.path.join(config["platform_options"]["wineDir"], "wineboot"), "-u" ]

    config["container"]["mounts"][user_wine_directory] = config["appconfig"]["internalAppDir"]
    config["container"]["mounts"][os.path.join(config["appDirs"]["windows"], config["appconfig"]["appname"], "drive_c")] = os.path.join(config["appconfig"]["internalAppDir"], "drive_c")

    config["container"]["environment"] = { "DISPLAY": config["display"] }

    if config["platform_options"]["debug"]:
        # Cribbing proton options
        config["container"]["environment"]["WINEDEBUG"] = "+timestamp,+pid,+tid,+seh,+debugstr,+loaddll,+mscoree"
        config["container"]["environment"]["DXVK_LOG_LEVEL"] = "info"
        config["container"]["environment"]["VKD3D_DEBUG"] = "warn"
        config["container"]["environment"]["WINE_MONO_TRACE"] = "E:System.NotImplementedException"
    else:
        config["container"]["environment"]["WINEDEBUG"] = "-all"
        config["container"]["environment"]["DXVK_LOG_LEVEL"] = "none"
        config["container"]["environment"]["VKD3D_DEBUG"] = "none"

    if not config["platform_options"]["esync"]:
        config["container"]["environment"]["WINEESYNC"] = 0
    else:
        config["container"]["environment"]["WINEESYNC"] = 1

    if config["platform_options"]["koku_hack"]:
            LD_PRELOAD.append(os.path.join(config["appconfig"]["internalAppDir"], "koku-xinput.wine.so"))
        
    if not config["platform_options"]["pba"]:
        config["container"]["environment"]["PBA_DISABLE"] = 1
        config["container"]["environment"]["PBA_ENABLE"] = 0
    else:
        config["container"]["environment"]["PBA_DISABLE"] = 0
        config["container"]["environment"]["PBA_ENABLE"] = 1
        
    if not "workingdir" in config["container"]:
        config["container"]["workingDir"] = os.path.join(config["appconfig"]["internalAppDir"], config["appconfig"]["exepath"])

    # This is basically a hack in case the program in question absolutely won't cooperate.
    if config["appconfig"]["wrapper"]:
        config["container"]["entrypoint"] = [ os.path.join(config["appconfig"]["internalAppDir"], config["appconfig"]["exepath"],
                                              config["appconfig"]["executable"]), config["appconfig"]["programArgs"] ]
    else:
        config["container"]["entrypoint"] = [ os.path.join(config["platform_options"]["wineDir"], "wine"),
                                              os.path.join(config["appconfig"]["internalAppDir"], config["appconfig"]["exepath"],
                                              config["appconfig"]["executable"]), config["appconfig"]["programArgs"] ]

    return config
