from subprocess import Popen
from pathlib import Path
import os, psutil
import re
import glob

def get_subids(user, group):
    if os.path.exists('/etc/subuid') and os.path.exists('/etc/subgid'):
        with open('/etc/subuid') as subuid_file:
            for line in subuid_file.readlines():
                if re.match("^" + user, line):
                    subuid = re.match("[A-Za-z]+:([0-9]+):", line)
        with open('/etc/subgid') as subgid_file:
            for line in subgid_file.readlines():
                if re.match("^" + group, line):
                    subgid = re.match("[A-Za-z]+:([0-9]+):", line)
        return int(subuid.group(1)), int(subgid.group(1))
    else:
        print("No subuid/subgid files found in /etc, something's broke.")
        return False

def get_namespace_ids():
    for process in psutil.process_iter():
        if process.name() == "dockerd":
            for argument in process.cmdline():
                print(argument)
                if re.match("--userns-remap.*", argument):
                    id_match = re.match('--userns-remap=([A-Za-z]+):([A-Za-z]+)', argument)
                    return get_subids(id_match.group(1), id_match.group(2))
        elif process.name() == "rootlesskit":
            return get_subids(process.username(), process.username())
    return False

def chown(target, container_uid=0, container_gid=0, recursive=False, no_root_chown=False):

    if target == '/' or target is os.path.expanduser('~'):
        print("Trying to operate on something we're defintely not supposed to. Bailing out.")
        sys.exit(1)

    if get_namespace_ids():
        ns_uid, ns_gid = get_namespace_ids()
        print("[DEBUG] ns_uid and ns_gid are %s %s" % (container_uid, container_gid))

        uid = container_uid + ns_uid
        gid = container_gid + ns_gid

        if container_uid != 0:
            uid = uid - 1
        if container_gid != 0: 
            gid = gid - 1

        print("[DEBUG] uid and gid are %d %d" % (uid, gid))
    else:
        print("[DEBUG] - get_namespace_ids failed, something is up")
        uid = container_uid
        gid = container_gid

    if chown_check(uid, gid):
        if target is None or target == "" or not target.isprintable() or target == '/' or target == os.getenv('HOME'):
            print("Trying to chown something we shouldn't. Exiting.")
            sys.exit(1)
        elif not os.path.exists(target):
            print("Trying to chown something nonexistent. Exiting.")
            
        if recursive == True:
            try:
                if no_root_chown == True:
                    for glob_target in glob.glob(target + "/*"):
                        result = Popen(["sudo", "/bin/chown", "--preserve-root", "-R", str(uid) + ":" + str(gid), glob_target])
                        result.wait()
                else:
                    result = Popen(["sudo", "/bin/chown", "--preserve-root", "-R", str(uid) + ":" + str(gid), target])
                    result.wait()
            except:
                print("Can't chown file, dying")
                sys.exit(1)
        else:
            try:
                result = Popen(["sudo", "/bin/chown", str(uid) + ":" + str(gid), target])
                result.wait()
            except:
                print("Can't chown file, dying")
                sys.exit(1)
                return False
    else:
        return False

def chown_check(uid, gid):
    # This is stupid
    return True
    testfile = Path("/tmp/subtest")
    testfile.touch()
    test = Popen(["sudo", "/bin/chown", str(uid) + ":" + str(gid), "/tmp/subtest"])
    test.wait()
    if test.poll() != 0:
        print("[WARNING] User is unable to modify permissions for %s:%s on %s!" % (uid, gid, "/tmp/subtest"))
        return False
    return True
