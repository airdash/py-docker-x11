import re, os
import subprocess
import hashlib
import shutil

def pull(driver_cache_path, docker_build_path):
    modinfo_output = subprocess.check_output(["modinfo", "nvidia"]).decode('utf-8').splitlines()
    BUF_SIZE = 65536
    md5_current = hashlib.md5()
    md5_latest = hashlib.md5()

    for line in modinfo_output:
        if re.match("^version\:\s+([0-9.]+)", line):
            driver_version = re.match("^version\:\s+([0-9.]+)", line)[1]
            current_driver_path = os.path.join(driver_cache_path, "NVIDIA-Linux-x86_64-" + driver_version + ".run")
            docker_build_driver_path = os.path.join(docker_build_path, "files", "nvidia-driver.run")

            if not os.path.exists(current_driver_path):
                print("Pulling driver %s:" % driver_version)
                try:
                    subprocess.check_output(["wget", "-O", current_driver_path,
                                             "https://us.download.nvidia.com/XFree86/Linux-x86_64/" + driver_version +
                                             "/NVIDIA-Linux-x86_64-" + driver_version + ".run"])
                    shutil.copy2(current_driver_path, docker_build_driver_path)
                    break
                except Exception as e:
                    print("Unable to pull the latest nVidia driver for the image! Aborting.")
                    print("Error: %s" % e)
                    sys.exit(1)

            if not os.path.exists(docker_build_driver_path):
                shutil.copy2(current_driver_path, docker_build_driver_path)
                break
            else:
                with open(current_driver_path, 'rb') as current_driver:
                    while True:
                        data = current_driver.read(BUF_SIZE)
                        if not data:
                            break
                        md5_current.update(data)
                with open(docker_build_driver_path, 'rb') as docker_driver:
                    while True:
                        data = docker_driver.read(BUF_SIZE)
                        if not data:
                            break
                        md5_latest.update(data)
                print("md5sum of current driver: {0}".format(md5_current.hexdigest()))
                print("md5sum of present driver: {0}".format(md5_latest.hexdigest()))

                if md5_current.hexdigest() != md5_latest.hexdigest():
                    shutil.copy2(current_driver_path, docker_build_driver_path)
                else:
                    print("Checksums match, nothing to do.")
                break

